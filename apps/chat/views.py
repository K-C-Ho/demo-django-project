from django.shortcuts import get_object_or_404, redirect, render
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Max
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from apps.accounts.models import User
from .models import ChatRoom, ChatRoomMembership, Message
from .forms import ChatRoomForm
from .redis_utils import RedisUnreadCount, RedisPresence
from .tasks import generate_thumbnail

@login_required
def room_list_view(request):
    """Display list of chat rooms."""
    # Get public rooms
    public_rooms = ChatRoom.objects.filter(
        room_type='public',
        is_active=True
    ).annotate(
        annotated_member_count=Count('memberships', filter=Q(memberships__is_active=True)),
        last_message_time=Max('messages__created_at')
    ).order_by('-last_message_time')

    # Get user's private rooms
    user_memberships = ChatRoomMembership.objects.filter(
        user=request.user,
        is_active=True
    ).select_related('room').exclude(room__room_type='public')
    
    private_rooms = [m.room for m in user_memberships]

    # Get unread counts
    unread = RedisUnreadCount()
    unread_counts = {}
    try:
        unread_counts = unread._get_unread_rooms(str(request.user.id))
    except Exception:
        pass

    context = {
        'public_rooms': public_rooms,
        'private_rooms': private_rooms,
        'unread_counts': unread_counts,
    }
    return render(request, 'chat/room_list.html', context)

@login_required
def create_room_view(request):
    """Create a new chat room."""
    if request.method == 'POST':
        form = ChatRoomForm(request.POST, request.FILES)
        if form.is_valid():
            room = form.save(commit=False)
            room.owner = request.user
            
            # Generate unique slug
            base_slug = slugify(room.name)
            slug = base_slug
            counter = 1
            while ChatRoom.objects.filter(slug=slug).exists():
                slug = f'{base_slug}-{counter}'
                counter += 1
            room.slug = slug
            
            room.save()
            messages.success(request, _('Room "%(room_name)s" created successfully!') % {'room_name': room.name})
            return redirect('chat:room_detail', room_slug=room.slug)
    else:
        form = ChatRoomForm()

    return render(request, 'chat/create_room.html', {'form': form})

@login_required
def create_direct_message(request):
    """Create a direct message room with another user."""
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        
        try:
            other_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            messages.error(request, _('User not found.'))
            return redirect('chat:room_list')

        if other_user == request.user:
            messages.error(request, _('You cannot start a chat with yourself.'))
            return redirect('chat:room_list')

        # Check if DM room already exists
        user_ids = sorted([str(request.user.id), str(other_user.id)])
        dm_slug = f'dm-{user_ids[0][:8]}-{user_ids[1][:8]}'

        room, created = ChatRoom.objects.get_or_create(
            slug=dm_slug,
            defaults={
                'name': f'{request.user.username} & {other_user.username}',
                'room_type': 'direct',
                'owner': request.user,
            }
        )

        if created:
            room.add_member(request.user)
            room.add_member(other_user)

        return redirect('chat:room_detail', room_slug=room.slug)

    return redirect('chat:room_list')

@login_required
def room_detail_view(request, room_slug):
    """Display chat room detail/interface."""
    room = get_object_or_404(ChatRoom, slug=room_slug, is_active=True)

    # Check access
    if not room.is_member(request.user):
        if room.room_type == 'public':
            # Auto-join public rooms
            room.add_member(request.user)
        else:
            messages.error(request, 'You do not have access to this room.')
            return redirect('chat:room_list')

    # Get room members
    memberships = ChatRoomMembership.objects.filter(
        room=room,
        is_active=True
    ).select_related('user').order_by('user__username')

    # Get online users in room
    presence = RedisPresence()
    online_user_ids = []
    try:
        online_user_ids = presence._get_room_users(str(room.id))
    except Exception:
        pass

    context = {
        'room': room,
        'memberships': memberships,
        'online_user_ids': online_user_ids,
    }
    return render(request, 'chat/room_detail.html', context)

@login_required
def edit_room_view(request, room_slug):
    """Edit a chat room."""
    room = get_object_or_404(ChatRoom, slug=room_slug)

    # Check if user is owner or admin
    membership = ChatRoomMembership.objects.filter(
        room=room,
        user=request.user,
        role__in=['owner', 'admin']
    ).first()

    if not membership and room.owner != request.user:
        messages.error(request, 'You do not have permission to edit this room.')
        return redirect('chat:room_detail', room_slug=room_slug)

    if request.method == 'POST':
        form = ChatRoomForm(request.POST, request.FILES, instance=room)
        if form.is_valid():
            form.save()
            messages.success(request, 'Room updated successfully!')
            return redirect('chat:room_detail', room_slug=room.slug)
    else:
        form = ChatRoomForm(instance=room)

    return render(request, 'chat/edit_room.html', {'form': form, 'room': room})

@login_required
def delete_room_view(request, room_slug):
    """Delete a chat room."""
    room = get_object_or_404(ChatRoom, slug=room_slug)

    if room.owner != request.user:
        messages.error(request, 'Only the room owner can delete this room.')
        return redirect('chat:room_detail', room_slug=room_slug)

    if request.method == 'POST':
        room_name = room.name
        room.delete()
        messages.success(request, f'Room "{room_name}" has been deleted.')
        return redirect('chat:room_list')

    return render(request, 'chat/delete_room.html', {'room': room})

@login_required
def leave_room(request, room_slug):
    """Leave a chat room."""
    room = get_object_or_404(ChatRoom, slug=room_slug)

    if room.owner == request.user:
        messages.error(request, 'Room owner cannot leave. Delete the room instead.')
        return redirect('chat:room_detail', room_slug=room_slug)

    room.remove_member(request.user)
    messages.info(request, f'You have left "{room.name}".')
    return redirect('chat:room_list')

@login_required
def join_room(request, room_slug):
    """Join a chat room."""
    room = get_object_or_404(ChatRoom, slug=room_slug, is_active=True)

    if room.room_type == 'private':
        messages.error(request, 'This is a private room. You need an invitation.')
        return redirect('chat:room_list')

    room.add_member(request.user)
    messages.success(request, f'You have joined "{room.name}"!')
    return redirect('chat:room_detail', room_slug=room_slug)

@login_required
def invite_to_room(request, room_slug):
    """Invite a user to a private room."""
    room = get_object_or_404(ChatRoom, slug=room_slug)

    # Check permission
    membership = ChatRoomMembership.objects.filter(
        room=room,
        user=request.user,
        role__in=['owner', 'admin', 'moderator']
    ).first()

    if not membership:
        messages.error(request, 'You do not have permission to invite users.')
        return redirect('chat:room_detail', room_slug=room_slug)

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        
        try:
            user = User.objects.get(username=username)
            if room.is_member(user):
                messages.info(request, f'{username} is already a member.')
            else:
                room.add_member(user)
                messages.success(request, f'{username} has been invited to the room.')
        except User.DoesNotExist:
            messages.error(request, f'User "{username}" not found.')

    return redirect('chat:room_detail', room_slug=room_slug)

@login_required
@require_POST
def upload_file(request, room_slug):
    """Handle file upload for a chat room."""
    room = get_object_or_404(ChatRoom, slug=room_slug)

    if not room.can_send_message(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    file = request.FILES.get('file')
    if not file:
        return JsonResponse({'error': 'No file provided'}, status=400)

    # Validate file
    max_size = settings.CHAT_SETTINGS.get('MAX_FILE_SIZE_MB', 10) * 1024 * 1024
    allowed_types = settings.CHAT_SETTINGS.get('ALLOWED_FILE_TYPES', [])

    if file.size > max_size:
        return JsonResponse({'error': 'File too large'}, status=400)

    if file.content_type not in allowed_types:
        return JsonResponse({'error': 'File type not allowed'}, status=400)

    # Create message with file
    message = Message.objects.create(
        room=room,
        sender=request.user,
        message_type='file' if not file.content_type.startswith('image') else 'image',
        content=file.name,
        file=file,
        file_name=file.name,
        file_size=file.size,
    )

    # Generate thumbnail for images (async task)
    if file.content_type.startswith('image'):
        generate_thumbnail.delay(str(message.id))

    return JsonResponse({
        'message_id': str(message.id),
        'file_url': message.file.url,
        'file_name': message.file_name,
        'file_size': message.file_size,
    })

@login_required
def search_messages(request, room_slug):
    """Search messages in a room."""
    room = get_object_or_404(ChatRoom, slug=room_slug)

    if not room.is_member(request.user):
        return JsonResponse({'error': 'Access denied'}, status=403)

    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'messages': []})

    messages_qs = Message.objects.filter(
        room=room,
        content__icontains=query,
        is_deleted=False
    ).select_related('sender').order_by('-created_at')[:50]

    results = [
        {
            'id': str(msg.id),
            'content': msg.content,
            'sender': msg.sender.username if msg.sender else 'System',
            'timestamp': msg.created_at.isoformat(),
        }
        for msg in messages_qs
    ]

    return JsonResponse({'messages': results})
