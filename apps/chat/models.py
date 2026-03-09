from datetime import timezone
import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class ChatRoom(models.Model):
    """
    Model for chat rooms (both public and private).
    """
    ROOM_TYPES = [
        ('public', _('Public')),
        ('private', _('Private')),
        ('direct', _('Direct Message')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    room_type = models.CharField(max_length=10, choices=ROOM_TYPES, default='public')
    
    # Room settings
    is_active = models.BooleanField(default=True)
    max_members = models.PositiveIntegerField(default=100)
    
    # Encryption (for E2E demo)
    is_encrypted = models.BooleanField(default=False)
    
    # Room image
    image = models.ImageField(upload_to='room_images/', null=True, blank=True)
    
    # Ownership
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='owned_rooms'
    )
    
    # Members (for private rooms)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='ChatRoomMembership',
        related_name='chat_rooms'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'chat_rooms'
        verbose_name = _('Chat Room')
        verbose_name_plural = _('Chat Rooms')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.room_type})'

    @property
    def channel_group_name(self):
        """Return the Channels group name for this room."""
        return f'chat_{self.slug}'

    @property
    def member_count(self):
        """Return the number of members in the room."""
        return self.memberships.filter(is_active=True).count()

    def add_member(self, user, role='member'):
        """Add a user to the room."""
        membership, created = ChatRoomMembership.objects.get_or_create(
            room=self,
            user=user,
            defaults={'role': role}
        )
        if not created:
            membership.is_active = True
            membership.save(update_fields=['is_active'])
        return membership

    def remove_member(self, user):
        """Remove a user from the room."""
        ChatRoomMembership.objects.filter(room=self, user=user).update(is_active=False)

    def is_member(self, user):
        """Check if user is a member of the room."""
        if self.room_type == 'public':
            return True
        return self.memberships.filter(user=user, is_active=True).exists()

    def can_send_message(self, user):
        """Check if user can send messages in this room."""
        if not self.is_active:
            return False
        membership = self.memberships.filter(user=user, is_active=True).first()
        if membership and membership.is_muted:
            return False
        return self.is_member(user)

class ChatRoomMembership(models.Model):
    """
    Through model for ChatRoom members with additional metadata.
    """
    ROLE_CHOICES = [
        ('owner', _('Owner')),
        ('admin', _('Admin')),
        ('moderator', _('Moderator')),
        ('member', _('Member')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='room_memberships'
    )
    
    # Role and permissions
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='member')
    is_active = models.BooleanField(default=True)
    is_muted = models.BooleanField(default=False)
    
    # Notification settings
    notifications_enabled = models.BooleanField(default=True)
    
    # Last read message (for unread count)
    last_read_message = models.ForeignKey(
        'Message',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )
    last_read_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'chat_room_memberships'
        unique_together = ['room', 'user']
        verbose_name = _('Chat Room Membership')
        verbose_name_plural = _('Chat Room Memberships')

    def __str__(self):
        return f'{self.user.username} in {self.room.name}'

    def mark_as_read(self, message=None):
        """Mark messages as read up to a specific message."""
        self.last_read_message = message
        self.last_read_at = timezone.now()
        self.save(update_fields=['last_read_message', 'last_read_at'])

class Message(models.Model):
    """
    Model for chat messages.
    """
    MESSAGE_TYPES = [
        ('text', _('Text')),
        ('image', _('Image')),
        ('file', _('File')),
        ('system', _('System')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_messages'
    )
    
    # Message content
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPES, default='text')
    content = models.TextField()
    
    # For encrypted messages
    is_encrypted = models.BooleanField(default=False)
    
    # For replies
    reply_to = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='replies'
    )
    
    # File attachment
    file = models.FileField(upload_to='chat_files/', null=True, blank=True)
    file_name = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(null=True, blank=True)
    thumbnail = models.ImageField(upload_to='chat_thumbnails/', null=True, blank=True)
    
    # Message status
    is_edited = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'chat_messages'
        verbose_name = _('Message')
        verbose_name_plural = _('Messages')
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['room', 'created_at']),
            models.Index(fields=['sender', 'created_at']),
        ]

    def __str__(self):
        sender_name = self.sender.username if self.sender else _('System')
        return f'{sender_name}: {self.content[:50]}...'

    def edit(self, new_content):
        """Edit the message content."""
        self.content = new_content
        self.is_edited = True
        self.edited_at = timezone.now()
        self.save(update_fields=['content', 'is_edited', 'edited_at'])

    def soft_delete(self):
        """Soft delete the message."""
        self.is_deleted = True
        self.content = '[Message deleted]'
        self.save(update_fields=['is_deleted', 'content'])

    @property
    def display_content(self):
        """Return content for display (respects deletion)."""
        if self.is_deleted:
            return '[Message deleted]'
        return self.content

class MessageReaction(models.Model):
    """
    Model for message reactions (emoji reactions).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='reactions')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reactions'
    )
    emoji = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'message_reactions'
        unique_together = ['message', 'user', 'emoji']
        verbose_name = 'Message Reaction'
        verbose_name_plural = 'Message Reactions'

    def __str__(self):
        return f'{self.user.username} reacted {self.emoji} to message'


class MessageReadReceipt(models.Model):
    """
    Model for tracking who has read which messages.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='read_receipts')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='read_receipts'
    )
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'message_read_receipts'
        unique_together = ['message', 'user']
        verbose_name = 'Message Read Receipt'
        verbose_name_plural = 'Message Read Receipts'

    def __str__(self):
        return f'{self.user.username} read message at {self.read_at}'
