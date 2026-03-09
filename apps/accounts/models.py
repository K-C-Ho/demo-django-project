import uuid
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.forms import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from datetime import date

class User(AbstractUser):
    def validate_minimum_age(value):
        if value:
            age = (date.today() - value).days // 365
            if age < 13:
                raise ValidationError(
                    _("You must be at least 13 years old."),
                    code='too_young'
                )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    phone = models.CharField(
        _('phone number'),
        max_length=20,
        blank=True,
        null=True,
        validators=[RegexValidator(r'^\d+$', _('Phone number must contain only digits.'))]
    )
    date_of_birth = models.DateField(
        _('date of birth'), 
        blank=True, 
        null=True,
        validators=[validate_minimum_age]
    )

    # Pillow is required for ImageField
    avatar = models.ImageField(_('avatar'), upload_to='avatars/', blank=True, null=True)
    bio = models.TextField(_('bio'), max_length=500, blank=True, null=True)

    email_notifications = models.BooleanField(_('email notifications'), default=True)
    push_notifications = models.BooleanField(_('push notifications'), default=False)

    public_key = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'users'
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['-created_at']

    def __str__(self):
        return self.username

    @property
    def avatar_url(self):
        if self.avatar:
            return self.avatar.url
        return '/static/images/default-avatar.png'
    
    def update_last_seen(self):
        self.last_seen = timezone.now()
        self.save(update_fields=['last_seen'])

    def set_online(self, status=True):
        self.is_online = status
        if not status:
            self.last_seen = timezone.now()
        self.save(update_fields=['is_online', 'last_seen'])

class UserBlock(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    blocker = models.ForeignKey(User, related_name='blocking', on_delete=models.CASCADE)
    blocked = models.ForeignKey(User, related_name='blocked_by', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_blocks'
        unique_together = ('blocker', 'blocked')
        verbose_name = _('User Block')
        verbose_name_plural = _('User Blocks')

    def __str__(self):
        return f"{self.blocker.username} blocked {self.blocked.username}"

class Friendship(models.Model):
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('accepted', _('Accepted')),
        ('rejected', _('Rejected')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sender = models.ForeignKey(User, related_name='sent_requests', on_delete=models.CASCADE)
    receiver = models.ForeignKey(User, related_name='received_requests', on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'friendships'
        unique_together = ('sender', 'receiver')
        verbose_name = _('Friendship')
        verbose_name_plural = _('Friendships')

    def __str__(self):
        return f"{self.sender.username} -> {self.receiver.username} ({self.status})"
    
    def accept(self):
        self.status = 'accepted'
        self.save(update_fields=['status', 'updated_at'])

    def reject(self):
        self.status = 'rejected'
        self.save(update_fields=['status', 'updated_at'])
