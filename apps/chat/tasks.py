import json
import logging
import os
import time
from celery import shared_task
from django.conf import settings
from PIL import Image
from pywebpush import webpush, WebPushException
from .models import Message, ChatRoomMembership
from .redis_utils import get_redis_connection, RedisPresence
from apps.accounts.models import User
from apps.notifications.models import PushSubscription

logger = logging.getLogger(__name__)

@shared_task
def generate_thumbnail(message_id):
    """
    Generate a thumbnail for an image message.
    """    
    try:
        message = Message.objects.get(id=message_id)
        
        if not message.file or not message.file.name:
            return f'Message {message_id} has no file'
        
        # Check if it's an image
        if message.message_type != 'image':
            return f'Message {message_id} is not an image'
        
        # Open the image
        image_path = message.file.path
        img = Image.open(image_path)
        
        # Generate thumbnail
        thumbnail_size = settings.CHAT_SETTINGS.get('THUMBNAIL_SIZE', (200, 200))
        img.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
        
        # Save thumbnail
        thumbnail_dir = os.path.join(settings.MEDIA_ROOT, 'chat_thumbnails')
        os.makedirs(thumbnail_dir, exist_ok=True)
        
        filename = os.path.basename(message.file.name)
        thumbnail_name = f'thumb_{filename}'
        thumbnail_path = os.path.join(thumbnail_dir, thumbnail_name)
        
        img.save(thumbnail_path, quality=85)
        
        # Update message
        message.thumbnail = f'chat_thumbnails/{thumbnail_name}'
        message.save(update_fields=['thumbnail'])
        
        logger.info(f'Generated thumbnail for message {message_id}')
        return f'Thumbnail generated for message {message_id}'
    
    except Message.DoesNotExist:
        logger.error(f'Message {message_id} not found')
        return f'Message {message_id} not found'
    except Exception as e:
        logger.error(f'Error generating thumbnail for message {message_id}: {e}')
        raise

@shared_task
def cleanup_old_typing_indicators():
    """
    Clean up expired typing indicators from Redis.
    Runs periodically via Celery Beat.
    """
    redis = get_redis_connection()
    
    # Find all typing keys
    typing_keys = redis.keys('chat:room:*:typing')
    cleaned = 0
    
    for key in typing_keys:
        typing_data = redis.hgetall(key)
        current_time = time.time()
        
        for user_id, timestamp in typing_data.items():
            # Remove if older than 5 seconds
            if current_time - float(timestamp) > 5:
                redis.hdel(key, user_id)
                cleaned += 1
    
    logger.info(f'Cleaned up {cleaned} expired typing indicators')
    return f'Cleaned {cleaned} typing indicators'

@shared_task
def cleanup_offline_users():
    """
    Mark users as offline if their presence key has expired.
    Syncs Redis presence with database.
    """
    presence = RedisPresence()
    
    # Get users marked as online in database
    online_users = User.objects.filter(is_online=True)
    
    updated = 0
    for user in online_users:
        # Check if user is actually online in Redis
        if not presence._is_user_online(str(user.id)):
            user.set_online(False)
            updated += 1
    
    logger.info(f'Updated {updated} users to offline status')
    return f'Updated {updated} users'

@shared_task
def send_push_notification(user_id, title, body, data=None):
    """
    Send a push notification to a user.
    """
    try:
        subscriptions = PushSubscription.objects.filter(
            user_id=user_id,
            is_active=True
        )
        
        payload = json.dumps({
            'title': title,
            'body': body,
            'data': data or {}
        })
        
        vapid_settings = settings.WEBPUSH_SETTINGS
        
        for subscription in subscriptions:
            try:
                webpush(
                    subscription_info={
                        'endpoint': subscription.endpoint,
                        'keys': {
                            'p256dh': subscription.p256dh,
                            'auth': subscription.auth
                        }
                    },
                    data=payload,
                    vapid_private_key=vapid_settings['VAPID_PRIVATE_KEY'],
                    vapid_claims={
                        'sub': f"mailto:{vapid_settings['VAPID_ADMIN_EMAIL']}"
                    }
                )
            except WebPushException as e:
                if e.response and e.response.status_code == 410:
                    # Subscription expired, deactivate it
                    subscription.is_active = False
                    subscription.save()
                else:
                    logger.error(f'WebPush error for user {user_id}: {e}')
        
        return f'Sent push notification to user {user_id}'
    
    except Exception as e:
        logger.error(f'Error sending push notification: {e}')
        raise

@shared_task
def notify_new_message(message_id):
    """
    Send notifications for a new message to room members.
    """
    try:
        message = Message.objects.select_related('room', 'sender').get(id=message_id)
        room = message.room
        sender = message.sender
        
        # Get members who should be notified
        memberships = ChatRoomMembership.objects.filter(
            room=room,
            is_active=True,
            notifications_enabled=True
        ).exclude(user=sender).select_related('user')
        
        for membership in memberships:
            user = membership.user
            
            # Check if user has push notifications enabled
            if user.push_notifications:
                send_push_notification.delay(
                    str(user.id),
                    f'New message in {room.name}',
                    f'{sender.username}: {message.content[:100]}',
                    {'room_slug': room.slug, 'message_id': str(message.id)}
                )
        
        return f'Notifications sent for message {message_id}'
    
    except Message.DoesNotExist:
        return f'Message {message_id} not found'

@shared_task
def process_file_upload(message_id):
    """
    Process an uploaded file (virus scan, metadata extraction, etc.).
    """
    try:
        message = Message.objects.get(id=message_id)
        
        if not message.file:
            return f'Message {message_id} has no file'
        
        # Get file info
        file_path = message.file.path
        file_size = os.path.getsize(file_path)
        
        # Update file size if not set
        if not message.file_size:
            message.file_size = file_size
            message.save(update_fields=['file_size'])
        
        # If it's an image, generate thumbnail
        if message.message_type == 'image':
            generate_thumbnail.delay(str(message.id))
        
        logger.info(f'Processed file upload for message {message_id}')
        return f'File processed for message {message_id}'
    
    except Message.DoesNotExist:
        return f'Message {message_id} not found'
    except Exception as e:
        logger.error(f'Error processing file for message {message_id}: {e}')
        raise
