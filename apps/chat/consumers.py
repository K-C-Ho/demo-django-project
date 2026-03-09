import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings
from django.utils import timezone
from .models import ChatRoom, ChatRoomMembership, Message, MessageReadReceipt
from .redis_utils import RedisUnreadCount, RedisPresence, RedisTypingIndicator

logger = logging.getLogger(__name__)

class ChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for chat rooms.
    Handles real-time messaging, typing indicators, and presence.
    """

    async def connect(self):
        """
        Called when WebSocket connection is established.
        """
        self.room_slug = self.scope['url_route']['kwargs']['room_slug']
        self.room_group_name = f'chat_{self.room_slug}'
        self.user = self.scope['user']

        # Reject anonymous users
        if not self.user.is_authenticated:
            await self.close()
            return

        # Get room and verify membership
        self.room = await self.get_room()
        if not self.room:
            await self.close()
            return

        if not await self.can_access_room():
            await self.close()
            return

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        # Accept the WebSocket connection
        await self.accept()

        # Initialize Redis utilities
        self.presence = RedisPresence()
        self.typing = RedisTypingIndicator()
        self.unread = RedisUnreadCount()

        # Mark user as present in room
        await self.presence.add_user_to_room(str(self.room.id), str(self.user.id))

        # Notify others that user joined
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_join',
                'user_id': str(self.user.id),
                'username': self.user.username,
                'avatar_url': self.user.avatar_url,
            }
        )

        # Send room info and recent messages
        await self.send_room_info()

        logger.info(f'User {self.user.username} connected to room {self.room_slug}')

    async def disconnect(self, close_code):
        """
        Called when WebSocket connection is closed.
        """
        if hasattr(self, 'room') and self.room:
            # Remove user from room presence
            await self.presence.remove_user_from_room(str(self.room.id), str(self.user.id))

            # Clear typing indicator
            await self.typing.clear_typing(str(self.room.id), str(self.user.id))

            # Notify others that user left
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'user_leave',
                    'user_id': str(self.user.id),
                    'username': self.user.username,
                }
            )

            # Leave room group
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

            logger.info(f'User {self.user.username} disconnected from room {self.room_slug}')

    async def receive(self, text_data):
        """
        Called when a message is received from WebSocket.
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type', 'message')

            handlers = {
                'message': self.handle_message,
                'typing_start': self.handle_typing_start,
                'typing_stop': self.handle_typing_stop,
                'message_read': self.handle_message_read,
                'reaction': self.handle_reaction,
                'edit_message': self.handle_edit_message,
                'delete_message': self.handle_delete_message,
            }

            handler = handlers.get(message_type)
            if handler:
                await handler(data)
            else:
                logger.warning(f'Unknown message type: {message_type}')

        except json.JSONDecodeError:
            logger.error('Invalid JSON received')
        except Exception as e:
            logger.error(f'Error handling message: {e}')

    async def handle_message(self, data):
        """
        Handle incoming chat message.
        """
        content = data.get('content', '').strip()
        reply_to_id = data.get('reply_to')
        is_encrypted = data.get('is_encrypted', False)

        if not content:
            return

        # Check if user can send messages
        if not await self.can_send_message():
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'You cannot send messages in this room.'
            }))
            return

        # Create message in database
        message = await self.create_message(content, reply_to_id, is_encrypted)

        # Clear typing indicator
        await self.typing.clear_typing(str(self.room.id), str(self.user.id))

        # Broadcast message to room
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message_id': str(message.id),
                'content': message.display_content,
                'sender_id': str(self.user.id),
                'sender_username': self.user.username,
                'sender_avatar': self.user.avatar_url,
                'reply_to': reply_to_id,
                'is_encrypted': is_encrypted,
                'timestamp': message.created_at.isoformat(),
            }
        )

        # Update unread counts for other members
        await self.update_unread_counts(message)

    async def handle_typing_start(self, data):
        """
        Handle typing start indicator.
        """
        await self.typing.set_typing(str(self.room.id), str(self.user.id))
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'typing_indicator',
                'user_id': str(self.user.id),
                'username': self.user.username,
                'is_typing': True,
            }
        )

    async def handle_typing_stop(self, data):
        """
        Handle typing stop indicator.
        """
        await self.typing.clear_typing(str(self.room.id), str(self.user.id))
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'typing_indicator',
                'user_id': str(self.user.id),
                'username': self.user.username,
                'is_typing': False,
            }
        )

    async def handle_message_read(self, data):
        """
        Handle message read receipt.
        """
        message_id = data.get('message_id')
        if message_id:
            await self.mark_message_read(message_id)
            
            # Update membership last read
            await self.update_last_read(message_id)
            
            # Clear unread count
            await self.unread.clear_unread(str(self.room.id), str(self.user.id))

            # Broadcast read receipt
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'read_receipt',
                    'user_id': str(self.user.id),
                    'username': self.user.username,
                    'message_id': message_id,
                }
            )

    async def handle_reaction(self, data):
        """
        Handle message reaction.
        """
        message_id = data.get('message_id')
        emoji = data.get('emoji')
        
        if message_id and emoji:
            await self.toggle_reaction(message_id, emoji)
            
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'message_reaction',
                    'message_id': message_id,
                    'user_id': str(self.user.id),
                    'username': self.user.username,
                    'emoji': emoji,
                }
            )

    async def handle_edit_message(self, data):
        """
        Handle message edit.
        """
        message_id = data.get('message_id')
        new_content = data.get('content', '').strip()
        
        if message_id and new_content:
            success = await self.edit_message(message_id, new_content)
            if success:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'message_edited',
                        'message_id': message_id,
                        'content': new_content,
                        'edited_at': timezone.now().isoformat(),
                    }
                )

    async def handle_delete_message(self, data):
        """
        Handle message deletion.
        """
        message_id = data.get('message_id')
        
        if message_id:
            success = await self.delete_message(message_id)
            if success:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'message_deleted',
                        'message_id': message_id,
                    }
                )

    # Channel layer event handlers
    async def chat_message(self, event):
        """
        Send chat message to WebSocket.
        """
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message_id': event['message_id'],
            'content': event['content'],
            'sender_id': event['sender_id'],
            'sender_username': event['sender_username'],
            'sender_avatar': event['sender_avatar'],
            'reply_to': event.get('reply_to'),
            'is_encrypted': event.get('is_encrypted', False),
            'timestamp': event['timestamp'],
        }))

    async def user_join(self, event):
        """
        Send user join notification to WebSocket.
        """
        await self.send(text_data=json.dumps({
            'type': 'user_join',
            'user_id': event['user_id'],
            'username': event['username'],
            'avatar_url': event.get('avatar_url'),
        }))

    async def user_leave(self, event):
        """
        Send user leave notification to WebSocket.
        """
        await self.send(text_data=json.dumps({
            'type': 'user_leave',
            'user_id': event['user_id'],
            'username': event['username'],
        }))

    async def typing_indicator(self, event):
        """
        Send typing indicator to WebSocket.
        """
        # Don't send typing indicator to the user who is typing
        if event['user_id'] != str(self.user.id):
            await self.send(text_data=json.dumps({
                'type': 'typing',
                'user_id': event['user_id'],
                'username': event['username'],
                'is_typing': event['is_typing'],
            }))

    async def read_receipt(self, event):
        """
        Send read receipt to WebSocket.
        """
        await self.send(text_data=json.dumps({
            'type': 'read_receipt',
            'user_id': event['user_id'],
            'username': event['username'],
            'message_id': event['message_id'],
        }))

    async def message_reaction(self, event):
        """
        Send message reaction to WebSocket.
        """
        await self.send(text_data=json.dumps({
            'type': 'reaction',
            'message_id': event['message_id'],
            'user_id': event['user_id'],
            'username': event['username'],
            'emoji': event['emoji'],
        }))

    async def message_edited(self, event):
        """
        Send message edited notification to WebSocket.
        """
        await self.send(text_data=json.dumps({
            'type': 'message_edited',
            'message_id': event['message_id'],
            'content': event['content'],
            'edited_at': event['edited_at'],
        }))

    async def message_deleted(self, event):
        """
        Send message deleted notification to WebSocket.
        """
        await self.send(text_data=json.dumps({
            'type': 'message_deleted',
            'message_id': event['message_id'],
        }))

    # Helper methods
    async def send_room_info(self):
        """
        Send room information and recent messages to the connected user.
        """
        # Get online users in room
        online_users = await self.presence.get_room_users(str(self.room.id))
        
        # Get typing users
        typing_users = await self.typing.get_typing_users(str(self.room.id))
        
        # Get recent messages
        messages = await self.get_recent_messages()
        
        # Get unread count
        unread_count = await self.unread.get_unread_count(str(self.room.id), str(self.user.id))

        await self.send(text_data=json.dumps({
            'type': 'room_info',
            'room': {
                'id': str(self.room.id),
                'name': self.room.name,
                'slug': self.room.slug,
                'room_type': self.room.room_type,
                'is_encrypted': self.room.is_encrypted,
            },
            'online_users': online_users,
            'typing_users': typing_users,
            'messages': messages,
            'unread_count': unread_count,
        }))

    # Database operations (sync to async)
    @database_sync_to_async
    def get_room(self):
        """Get the chat room."""
        try:
            return ChatRoom.objects.get(slug=self.room_slug)
        except ChatRoom.DoesNotExist:
            return None

    @database_sync_to_async
    def can_access_room(self):
        """Check if user can access the room."""
        return self.room.is_member(self.user)

    @database_sync_to_async
    def can_send_message(self):
        """Check if user can send messages in the room."""
        return self.room.can_send_message(self.user)

    @database_sync_to_async
    def create_message(self, content, reply_to_id=None, is_encrypted=False):
        """Create a new message in the database."""
        reply_to = None
        if reply_to_id:
            try:
                reply_to = Message.objects.get(id=reply_to_id, room=self.room)
            except Message.DoesNotExist:
                pass

        return Message.objects.create(
            room=self.room,
            sender=self.user,
            content=content,
            reply_to=reply_to,
            is_encrypted=is_encrypted,
        )

    @database_sync_to_async
    def get_recent_messages(self, limit=50):
        """Get recent messages for the room."""
        limit = getattr(settings, 'CHAT_SETTINGS', {}).get('MESSAGE_HISTORY_LIMIT', limit)
        
        messages = Message.objects.filter(
            room=self.room
        ).select_related('sender', 'reply_to').order_by('-created_at')[:limit]
        
        return [
            {
                'id': str(msg.id),
                'content': msg.display_content,
                'sender_id': str(msg.sender.id) if msg.sender else None,
                'sender_username': msg.sender.username if msg.sender else 'System',
                'sender_avatar': msg.sender.avatar_url if msg.sender else None,
                'reply_to': str(msg.reply_to.id) if msg.reply_to else None,
                'is_encrypted': msg.is_encrypted,
                'is_edited': msg.is_edited,
                'is_deleted': msg.is_deleted,
                'timestamp': msg.created_at.isoformat(),
            }
            for msg in reversed(messages)
        ]

    @database_sync_to_async
    def mark_message_read(self, message_id):
        """Mark a message as read."""
        try:
            message = Message.objects.get(id=message_id, room=self.room)
            MessageReadReceipt.objects.get_or_create(
                message=message,
                user=self.user
            )
        except Message.DoesNotExist:
            pass

    @database_sync_to_async
    def update_last_read(self, message_id):
        """Update the last read message for the user's membership."""
        try:
            message = Message.objects.get(id=message_id, room=self.room)
            membership = ChatRoomMembership.objects.get(
                room=self.room,
                user=self.user
            )
            membership.mark_as_read(message)
        except (Message.DoesNotExist, ChatRoomMembership.DoesNotExist):
            pass

    @database_sync_to_async
    def toggle_reaction(self, message_id, emoji):
        """Toggle a reaction on a message."""
        from .models import MessageReaction
        try:
            message = Message.objects.get(id=message_id, room=self.room)
            reaction, created = MessageReaction.objects.get_or_create(
                message=message,
                user=self.user,
                emoji=emoji
            )
            if not created:
                reaction.delete()
        except Message.DoesNotExist:
            pass

    @database_sync_to_async
    def edit_message(self, message_id, new_content):
        """Edit a message (only sender can edit)."""
        try:
            message = Message.objects.get(
                id=message_id,
                room=self.room,
                sender=self.user
            )
            message.edit(new_content)
            return True
        except Message.DoesNotExist:
            return False

    @database_sync_to_async
    def delete_message(self, message_id):
        """Soft delete a message (only sender can delete)."""
        try:
            message = Message.objects.get(
                id=message_id,
                room=self.room,
                sender=self.user
            )
            message.soft_delete()
            return True
        except Message.DoesNotExist:
            return False

    async def update_unread_counts(self, message):
        """Update unread counts for all room members except sender."""
        members = await self.get_room_members()
        for member_id in members:
            if member_id != str(self.user.id):
                await self.unread.increment_unread(str(self.room.id), member_id)

    @database_sync_to_async
    def get_room_members(self):
        """Get list of room member IDs."""
        return list(
            ChatRoomMembership.objects.filter(
                room=self.room,
                is_active=True
            ).values_list('user_id', flat=True)
        )

class PresenceConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for global user presence.
    Tracks online/offline status across all rooms.
    """

    async def connect(self):
        """
        Called when WebSocket connection is established.
        """
        self.user = self.scope['user']

        if not self.user.is_authenticated:
            await self.close()
            return

        self.presence_group = 'presence'
        self.user_group = f'user_{self.user.id}'

        # Join presence group
        await self.channel_layer.group_add(
            self.presence_group,
            self.channel_name
        )

        # Join user-specific group for direct messages
        await self.channel_layer.group_add(
            self.user_group,
            self.channel_name
        )

        await self.accept()

        # Initialize Redis presence
        self.presence = RedisPresence()
        await self.presence.set_user_online(str(self.user.id))

        # Update database
        await self.set_user_online(True)

        # Broadcast online status
        await self.channel_layer.group_send(
            self.presence_group,
            {
                'type': 'presence_update',
                'user_id': str(self.user.id),
                'username': self.user.username,
                'is_online': True,
            }
        )

        logger.info(f'User {self.user.username} is now online')

    async def disconnect(self, close_code):
        """
        Called when WebSocket connection is closed.
        """
        if hasattr(self, 'user') and self.user.is_authenticated:
            # Mark user offline in Redis
            await self.presence.set_user_offline(str(self.user.id))

            # Update database
            await self.set_user_online(False)

            # Broadcast offline status
            await self.channel_layer.group_send(
                self.presence_group,
                {
                    'type': 'presence_update',
                    'user_id': str(self.user.id),
                    'username': self.user.username,
                    'is_online': False,
                }
            )

            # Leave groups
            await self.channel_layer.group_discard(
                self.presence_group,
                self.channel_name
            )
            await self.channel_layer.group_discard(
                self.user_group,
                self.channel_name
            )

            logger.info(f'User {self.user.username} is now offline')

    async def receive(self, text_data):
        """
        Handle incoming messages (heartbeat, etc.).
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'heartbeat':
                # Refresh online status
                await self.presence.set_user_online(str(self.user.id))
                await self.send(text_data=json.dumps({
                    'type': 'heartbeat_ack',
                    'timestamp': timezone.now().isoformat(),
                }))

            elif message_type == 'get_online_users':
                # Send list of online users
                online_users = await self.presence.get_all_online_users()
                await self.send(text_data=json.dumps({
                    'type': 'online_users',
                    'users': online_users,
                }))

        except json.JSONDecodeError:
            pass

    async def presence_update(self, event):
        """
        Send presence update to WebSocket.
        """
        await self.send(text_data=json.dumps({
            'type': 'presence',
            'user_id': event['user_id'],
            'username': event['username'],
            'is_online': event['is_online'],
        }))

    async def direct_message(self, event):
        """
        Handle direct messages sent to this user.
        """
        await self.send(text_data=json.dumps({
            'type': 'direct_message',
            'from_user_id': event['from_user_id'],
            'from_username': event['from_username'],
            'room_slug': event['room_slug'],
            'content': event['content'],
            'timestamp': event['timestamp'],
        }))

    @database_sync_to_async
    def set_user_online(self, status):
        """Update user's online status in database."""
        self.user.set_online(status)
