from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render, get_object_or_404
from .forms import UserProfileForm
from django.contrib import messages
from .models import Friendship, User, UserBlock
from django.db.models import Q

@login_required
def profile_view(request):
    """Display and edit user profile."""
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('accounts:profile')
    else:
        form = UserProfileForm(instance=request.user)
    
    return render(request, 'accounts/profile.html', {'form': form})

@login_required
def friends_list_view(request):
    """List all friends."""
    friendships = Friendship.objects.filter(
        Q(sender=request.user) | Q(receiver=request.user),
        status='accepted'
    ).select_related('sender', 'receiver')
    
    friends = []
    for friendship in friendships:
        if friendship.sender == request.user:
            friends.append(friendship.receiver)
        else:
            friends.append(friendship.sender)
    
    return render(request, 'accounts/friends_list.html', {'friends': friends})

@login_required
def search_users_view(request):
    """Search for users."""
    query = request.GET.get('q', '')
    users = []
    
    if query:
        users = User.objects.filter(
            Q(username__icontains=query) | Q(email__icontains=query)
        ).exclude(id=request.user.id)[:20]
    
    return render(request, 'accounts/search_users.html', {'users': users, 'query': query,})

@login_required
def user_profile_view(request, username):
    """View another user's profile."""
    user = get_object_or_404(User, username=username)
    
    # Check friendship status
    friendship = Friendship.objects.filter(
        Q(sender=request.user, receiver=user) | 
        Q(sender=user, receiver=request.user)
    ).first()
    
    # Check if blocked
    is_blocked = UserBlock.objects.filter(
        blocker=request.user, blocked=user
    ).exists()
    
    context = {
        'profile_user': user,
        'friendship': friendship,
        'is_blocked': is_blocked,
    }
    return render(request, 'accounts/user_profile.html', context)

@login_required
def friend_requests_view(request):
    """View pending friend requests."""
    received = Friendship.objects.filter(
        receiver=request.user, 
        status='pending'
    ).select_related('sender')
    
    sent = Friendship.objects.filter(
        sender=request.user, 
        status='pending'
    ).select_related('receiver')
    
    context = {
        'received_requests': received,
        'sent_requests': sent,
    }
    return render(request, 'accounts/friend_requests.html', context)

@login_required
def send_friend_request(request, user_id):
    """Send a friend request."""
    target_user = get_object_or_404(User, id=user_id)
    
    if target_user == request.user:
        messages.error(request, "You can't send a friend request to yourself.")
        return redirect('accounts:user_profile', username=target_user.username)
    
    # Check if request already exists
    existing = Friendship.objects.filter(
        Q(sender=request.user, receiver=target_user) |
        Q(sender=target_user, receiver=request.user)
    ).first()
    
    if existing:
        messages.info(request, 'Friend request already exists.')
    else:
        Friendship.objects.create(sender=request.user, receiver=target_user)
        messages.success(request, f'Friend request sent to {target_user.username}!')
    
    return redirect('accounts:user_profile', username=target_user.username)

@login_required
def accept_friend_request(request, request_id):
    """Accept a friend request."""
    friendship = get_object_or_404(
        Friendship, 
        id=request_id, 
        receiver=request.user, 
        status='pending'
    )
    friendship.accept()
    messages.success(request, f'You are now friends with {friendship.sender.username}!')
    return redirect('accounts:friend_requests')

@login_required
def reject_friend_request(request, request_id):
    """Reject a friend request."""
    friendship = get_object_or_404(
        Friendship, 
        id=request_id, 
        receiver=request.user, 
        status='pending'
    )
    friendship.reject()
    messages.info(request, 'Friend request rejected.')
    return redirect('accounts:friend_requests')

@login_required
def block_user(request, user_id):
    """Block a user."""
    target_user = get_object_or_404(User, id=user_id)
    
    if target_user == request.user:
        messages.error(request, "You can't block yourself.")
        return redirect('accounts:profile')
    
    UserBlock.objects.get_or_create(blocker=request.user, blocked=target_user)
    
    # Remove any friendship
    Friendship.objects.filter(
        Q(sender=request.user, receiver=target_user) |
        Q(sender=target_user, receiver=request.user)
    ).delete()
    
    messages.success(request, f'{target_user.username} has been blocked.')
    return redirect('accounts:user_profile', username=target_user.username)

@login_required
def unblock_user(request, user_id):
    """Unblock a user."""
    target_user = get_object_or_404(User, id=user_id)
    UserBlock.objects.filter(blocker=request.user, blocked=target_user).delete()
    messages.success(request, f'{target_user.username} has been unblocked.')
    return redirect('accounts:user_profile', username=target_user.username)
