from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.room_list_view, name='room_list'),
    path('create/', views.create_room_view, name='create_room'),

    # Direct messages
    path('dm/create/', views.create_direct_message, name='create_direct_message'),

    # Room operations
    path('room/<slug:room_slug>/', views.room_detail_view, name='room_detail'),
    path('room/<slug:room_slug>/edit/', views.edit_room_view, name='edit_room'),
    path('room/<slug:room_slug>/delete/', views.delete_room_view, name='delete_room'),
    path('room/<slug:room_slug>/leave/', views.leave_room, name='leave_room'),
    path('room/<slug:room_slug>/join/', views.join_room, name='join_room'),
    path('room/<slug:room_slug>/invite/', views.invite_to_room, name='invite_to_room'),

    # File upload
    path('room/<slug:room_slug>/upload/', views.upload_file, name='upload_file'),
    
    # Search
    path('room/<slug:room_slug>/search/', views.search_messages, name='search_messages'),
]
