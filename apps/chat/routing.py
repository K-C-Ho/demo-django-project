from django.urls import re_path
from apps.chat import consumers

websocket_urlpatterns = [
    # Chat room WebSocket
    re_path(
        r'ws/chat/(?P<room_slug>[\w-]+)/$',
        consumers.ChatConsumer.as_asgi()
    ),
    
    # Global presence WebSocket
    re_path(
        r'ws/presence/$',
        consumers.PresenceConsumer.as_asgi()
    ),
]
