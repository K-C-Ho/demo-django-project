from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('', views.profile_view, name='profile'),
    path('friends/', views.friends_list_view, name='friends_list'),
    path('search/', views.search_users_view, name='search_users'),
    path('user/<str:username>/', views.user_profile_view, name='user_profile'),
    path('friends/requests/', views.friend_requests_view, name='friend_requests'),
    path('friends/request/<uuid:user_id>/', views.send_friend_request, name='send_friend_request'),
    path('friends/accept/<uuid:request_id>/', views.accept_friend_request, name='accept_friend_request'),
    path('friends/reject/<uuid:request_id>/', views.reject_friend_request, name='reject_friend_request'),
    path('block/<uuid:user_id>/', views.block_user, name='block_user'),
    path('unblock/<uuid:user_id>/', views.unblock_user, name='unblock_user'),
]
