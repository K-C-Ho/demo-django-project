import time
import redis
import json
from django.conf import settings
from asgiref.sync import sync_to_async

def get_redis_connection():
    """Get a Redis connection."""
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD,
        decode_responses=True
    )

class RedisUnreadCount:
    """
    Manages unread message counts using Redis.
    Tracks how many unread messages each user has in each room.
    """
    
    UNREAD_KEY = 'chat:user:{user_id}:room:{room_id}:unread'
    USER_UNREAD_ROOMS_KEY = 'chat:user:{user_id}:unread_rooms'

    def __init__(self):
        self.redis = get_redis_connection()

    @sync_to_async
    def increment_unread(self, room_id, user_id):
        """Sync method to increment unread."""
        with self.redis.pipeline() as pipe:
            key = self.UNREAD_KEY.format(user_id=user_id, room_id=room_id)
            pipe.incr(key)
            pipe.sadd(self.USER_UNREAD_ROOMS_KEY.format(user_id=user_id), room_id)
            pipe.execute()

    @sync_to_async
    def get_unread_count(self, room_id, user_id):
        """Sync method to get unread count."""
        key = self.UNREAD_KEY.format(user_id=user_id, room_id=room_id)
        count = self.redis.get(key)
        return int(count) if count else 0

    @sync_to_async
    def clear_unread(self, room_id, user_id):
        """Sync method to clear unread count."""
        with self.redis.pipeline() as pipe:
            key = self.UNREAD_KEY.format(user_id=user_id, room_id=room_id)
            pipe.delete(key)
            pipe.srem(self.USER_UNREAD_ROOMS_KEY.format(user_id=user_id), room_id)
            pipe.execute()

    @sync_to_async
    def get_total_unread(self, user_id):
        """Sync method to get total unread count."""
        rooms = self.redis.smembers(self.USER_UNREAD_ROOMS_KEY.format(user_id=user_id))
        total = 0
        for room_id in rooms:
            key = self.UNREAD_KEY.format(user_id=user_id, room_id=room_id)
            count = self.redis.get(key)
            if count:
                total += int(count)
        return total

    @sync_to_async
    def get_unread_rooms(self, user_id):
        """Sync method to get unread rooms."""
        rooms = self.redis.smembers(self.USER_UNREAD_ROOMS_KEY.format(user_id=user_id))
        result = {}
        for room_id in rooms:
            key = self.UNREAD_KEY.format(user_id=user_id, room_id=room_id)
            count = self.redis.get(key)
            if count and int(count) > 0:
                result[room_id] = int(count)
        return result

class RedisPresence:
    """
    Manages user presence using Redis.
    Tracks which users are online globally and in specific rooms.
    """
    
    # Redis key prefixes
    ONLINE_USERS_KEY = 'chat:online_users'
    ROOM_USERS_KEY = 'chat:room:{room_id}:users'
    USER_ROOMS_KEY = 'chat:user:{user_id}:rooms'
    USER_INFO_KEY = 'chat:user:{user_id}:info'
    
    # TTL for presence data (30 seconds, refreshed by heartbeat)
    PRESENCE_TTL = 30

    def __init__(self):
        self.redis = get_redis_connection()

    @sync_to_async
    def set_user_online(self, user_id):
        """Sync method to set user online."""
        with self.redis.pipeline() as pipe:
            # Add to online users set
            pipe.sadd(self.ONLINE_USERS_KEY, user_id)
            # Set expiry using a separate key for TTL
            pipe.setex(f'chat:user:{user_id}:online', self.PRESENCE_TTL, '1')
            pipe.execute()

    @sync_to_async
    def set_user_offline(self, user_id):
        """Sync method to set user offline."""
        with self.redis.pipeline() as pipe:
            # Remove from online users set
            pipe.srem(self.ONLINE_USERS_KEY, user_id)
            # Delete online key
            pipe.delete(f'chat:user:{user_id}:online')
            # Remove from all rooms
            rooms = self.redis.smembers(self.USER_ROOMS_KEY.format(user_id=user_id))
            for room_id in rooms:
                pipe.srem(self.ROOM_USERS_KEY.format(room_id=room_id), user_id)
            pipe.delete(self.USER_ROOMS_KEY.format(user_id=user_id))
            pipe.execute()

    @sync_to_async
    def is_user_online(self, user_id):
        """Sync method to check if user is online."""
        return self.redis.exists(f'chat:user:{user_id}:online') > 0

    @sync_to_async
    def get_all_online_users(self):
        """Sync method to get all online users."""
        return list(self.redis.smembers(self.ONLINE_USERS_KEY))

    @sync_to_async
    def add_user_to_room(self, room_id, user_id):
        """Sync method to add user to room."""
        with self.redis.pipeline() as pipe:
            # Add user to room's user set
            pipe.sadd(self.ROOM_USERS_KEY.format(room_id=room_id), user_id)
            # Add room to user's room set
            pipe.sadd(self.USER_ROOMS_KEY.format(user_id=user_id), room_id)
            pipe.execute()

    @sync_to_async
    def remove_user_from_room(self, room_id, user_id):
        """Sync method to remove user from room."""
        with self.redis.pipeline() as pipe:
            # Remove user from room's user set
            pipe.srem(self.ROOM_USERS_KEY.format(room_id=room_id), user_id)
            # Remove room from user's room set
            pipe.srem(self.USER_ROOMS_KEY.format(user_id=user_id), room_id)
            pipe.execute()

    @sync_to_async
    def get_room_users(self, room_id):
        """Sync method to get room users."""
        return list(self.redis.smembers(self.ROOM_USERS_KEY.format(room_id=room_id)))

    @sync_to_async
    def get_room_user_count(self, room_id):
        """Sync method to get room user count."""
        return self.redis.scard(self.ROOM_USERS_KEY.format(room_id=room_id))

class RedisTypingIndicator:
    """
    Manages typing indicators using Redis.
    Tracks who is typing in which rooms.
    """
    
    TYPING_KEY = 'chat:room:{room_id}:typing'
    TYPING_TTL = 5  # Typing indicator expires after 5 seconds

    def __init__(self):
        self.redis = get_redis_connection()

    @sync_to_async
    def set_typing(self, room_id, user_id):
        """Sync method to set typing."""
        key = self.TYPING_KEY.format(room_id=room_id)
        # Use hash with user_id as field and timestamp as value
        self.redis.hset(key, user_id, time.time())
        self.redis.expire(key, self.TYPING_TTL * 2)  # Give some buffer

    @sync_to_async
    def clear_typing(self, room_id, user_id):
        """Sync method to clear typing."""
        key = self.TYPING_KEY.format(room_id=room_id)
        self.redis.hdel(key, user_id)

    @sync_to_async
    def get_typing_users(self, room_id):
        """Sync method to get typing users."""
        key = self.TYPING_KEY.format(room_id=room_id)
        typing_data = self.redis.hgetall(key)
        
        # Filter out expired typing indicators
        current_time = time.time()
        active_typers = []
        for user_id, timestamp in typing_data.items():
            if current_time - float(timestamp) < self.TYPING_TTL:
                active_typers.append(user_id)
            else:
                # Clean up expired entry
                self.redis.hdel(key, user_id)
        
        return active_typers

    @sync_to_async
    def is_user_typing(self, room_id, user_id):
        """Sync method to check if user is typing."""
        key = self.TYPING_KEY.format(room_id=room_id)
        timestamp = self.redis.hget(key, user_id)
        if timestamp:
            return time.time() - float(timestamp) < self.TYPING_TTL
        return False

class RedisRateLimiter:
    """
    Rate limiter using Redis.
    Prevents spam and abuse.
    """
    
    RATE_LIMIT_KEY = 'chat:ratelimit:{user_id}:{action}'

    def __init__(self):
        self.redis = get_redis_connection()

    async def is_rate_limited(self, user_id, action, limit=10, window=60):
        """
        Check if user is rate limited.
        
        Args:
            user_id: User ID
            action: Action type (e.g., 'message', 'typing')
            limit: Maximum number of actions allowed
            window: Time window in seconds
        
        Returns:
            bool: True if rate limited, False otherwise
        """
        return await sync_to_async(self._is_rate_limited)(user_id, action, limit, window)

    def _is_rate_limited(self, user_id, action, limit, window):
        """Sync method to check rate limit."""
        import time
        key = self.RATE_LIMIT_KEY.format(user_id=user_id, action=action)
        current_time = time.time()
        
        pipe = self.redis.pipeline()
        # Remove old entries
        pipe.zremrangebyscore(key, 0, current_time - window)
        # Count current entries
        pipe.zcard(key)
        # Add new entry
        pipe.zadd(key, {str(current_time): current_time})
        # Set expiry
        pipe.expire(key, window)
        
        results = pipe.execute()
        count = results[1]
        
        return count >= limit


class RedisPubSub:
    """
    Redis Pub/Sub wrapper for real-time events.
    Used for cross-instance communication.
    """

    def __init__(self):
        self.redis = get_redis_connection()
        self.pubsub = self.redis.pubsub()

    def publish(self, channel, message):
        """Publish a message to a channel."""
        if isinstance(message, dict):
            message = json.dumps(message)
        self.redis.publish(channel, message)

    def subscribe(self, channel):
        """Subscribe to a channel."""
        self.pubsub.subscribe(channel)

    def listen(self):
        """Listen for messages."""
        for message in self.pubsub.listen():
            if message['type'] == 'message':
                data = message['data']
                if isinstance(data, bytes):
                    data = data.decode('utf-8')
                try:
                    yield json.loads(data)
                except json.JSONDecodeError:
                    yield data

    def close(self):
        """Close the connection."""
        self.pubsub.close()
