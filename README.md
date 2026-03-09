# Django Real-Time Chat Application

A full-featured real-time chat application built with **Django Channels**, **Redis**, **WebSockets**, and **PostgreSQL**. This project is designed for learning and practicing modern real-time web development with Django.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Django](https://img.shields.io/badge/Django-4.2+-green.svg)
![Redis](https://img.shields.io/badge/Redis-7+-red.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-blue.svg)

## Features

### Core Features
- **User Authentication** - Django Allauth integration (login, register, password reset)
- **Multiple Chat Rooms** - Public and private rooms
- **Real-Time Messaging** - WebSocket-based instant messaging
- **Message History** - Persisted in PostgreSQL
- **Online/Offline Status** - Redis-based presence tracking
- **Unread Message Count** - Redis-tracked unread counts

### Advanced Features
- **Direct Messages** - Private 1-on-1 conversations
- **Reply to Messages** - Thread-style replies
- **File/Image Upload** - With thumbnail generation (Celery)
- **Push Notifications** - WebPush support
- **Friend System** - Add friends, send/accept requests
- **User Blocking** - Block unwanted users

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend Framework | Django 5.2+ |
| Real-Time Layer | Django Channels 4.3+ |
| WebSocket Server | Daphne |
| Channel Layer | Redis 7+ (channels-redis) |
| Database | PostgreSQL 15+ |
| Task Queue | Celery |
| Authentication | Django Allauth |
| API | Django REST Framework |
| Frontend | Bootstrap 5 + Vanilla JS |
| Containerization | Docker & Docker Compose |

## Quick Start

### Option 1: Docker (Recommended)

```bash
# Copy environment file
cp .env.example .env

# Build and start all services
docker-compose up --build

# In another terminal, run:
# Generates the migration files
docker-compose exec django_app_service python manage.py makemigrations accounts chat notifications
# Applies them to create the tables
docker-compose exec django_app_service python manage.py migrate

# Create a superuser
docker-compose exec django_app_service python manage.py createsuperuser

# Open http://localhost:8000 in your browser
```

### Option 2: Local Development

```bash
# Prerequisites: Python 3.12+, PostgreSQL, Redis

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install drf-nested-routers

# Copy and configure environment
cp .env.example .env
# Edit .env with your database credentials

# Start Redis (required for Channels)
redis-server

# Start PostgreSQL and create database
# psql -U postgres
# CREATE DATABASE demo_db;
# CREATE USER chat_user WITH PASSWORD 'chat_password';
# GRANT ALL PRIVILEGES ON DATABASE demo_db TO chat_user;

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Start the development server (use Daphne for WebSocket support)
daphne -b 0.0.0.0 -p 8000 config.asgi:application

# In another terminal, start Celery worker
celery -A config worker -l info

# Open http://localhost:8000
```

## Usage Guide

### Creating a Chat Room

1. Log in to your account
2. Navigate to "Chat Rooms"
3. Click "Create New Room"
4. Fill in room details (name, type, description)
5. Click "Create Room"

### Joining a Room

- **Public Rooms**: Click on any room to auto-join
- **Private Rooms**: Wait for an invitation from room admin

### Real-Time Features

- **Messaging**: Type in the input box and press Enter
- **Online Status**: Green dot = online, gray = offline
- **Reply**: Click reply button to respond to a specific message

### Direct Messages

1. Go to a user's profile
2. Click "Send Message"
3. A private DM room will be created

## Redis Key Structure

The application uses Redis extensively for real-time features:

```
# User Presence
chat:online_users                    # Set of online user IDs
chat:user:{user_id}:online           # TTL key for user online status
chat:room:{room_id}:users            # Set of users in a room

# Typing Indicators
chat:room:{room_id}:typing           # Hash of user_id -> timestamp

# Unread Counts
chat:user:{user_id}:room:{room_id}:unread    # Unread message count
chat:user:{user_id}:unread_rooms             # Set of rooms with unread

# Rate Limiting
chat:ratelimit:{user_id}:{action}    # Sorted set for rate limiting
```

## WebSocket Protocol

### Connecting

```javascript
const socket = new WebSocket('ws://localhost:8000/ws/chat/room-slug/');
```

### Message Types

#### Client → Server

```json
// Send message
{"type": "message", "content": "Hello!", "reply_to": null}

// Typing indicators
{"type": "typing_start"}
{"type": "typing_stop"}

// Mark message as read
{"type": "message_read", "message_id": "uuid"}

// React to message
{"type": "reaction", "message_id": "uuid", "emoji": "👍"}

// Edit message
{"type": "edit_message", "message_id": "uuid", "content": "Updated"}

// Delete message
{"type": "delete_message", "message_id": "uuid"}
```

#### Server → Client

```json
// New message
{
  "type": "message",
  "message_id": "uuid",
  "content": "Hello!",
  "sender_id": "uuid",
  "sender_username": "john",
  "timestamp": "2024-01-15T10:30:00Z"
}

// User presence
{"type": "user_join", "user_id": "uuid", "username": "john"}
{"type": "user_leave", "user_id": "uuid", "username": "john"}

// Typing indicator
{"type": "typing", "user_id": "uuid", "username": "john", "is_typing": true}

// Room info (on connect)
{
  "type": "room_info",
  "room": {...},
  "online_users": ["uuid1", "uuid2"],
  "messages": [...],
  "unread_count": 5
}
```

## API Endpoints

### Authentication
- `GET /accounts/login/` - Login page
- `GET /accounts/signup/` - Registration page
- `GET /accounts/logout/` - Logout

### Chat API
- `GET /api/chat/rooms/` - List rooms
- `POST /api/chat/rooms/` - Create room
- `GET /api/chat/rooms/{slug}/` - Room details
- `POST /api/chat/rooms/{slug}/join/` - Join room
- `POST /api/chat/rooms/{slug}/leave/` - Leave room
- `GET /api/chat/rooms/{slug}/messages/` - Get messages

### User API
- `GET /api/accounts/users/me/` - Current user
- `PATCH /api/accounts/users/update_profile/` - Update profile
- `GET /api/accounts/users/search/?q=term` - Search users
- `POST /api/accounts/friendships/send_request/` - Send friend request

## Testing

```bash
# Run tests
python manage.py test

# Run tests with coverage
coverage run manage.py test
coverage report -m
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DEBUG` | Debug mode | `True` |
| `SECRET_KEY` | Django secret key | (required) |
| `POSTGRES_DB` | Database name | `chat_db` |
| `POSTGRES_USER` | Database user | `chat_user` |
| `POSTGRES_PASSWORD` | Database password | `chat_password` |
| `POSTGRES_HOST` | Database host | `localhost` |
| `REDIS_HOST` | Redis host | `localhost` |
| `REDIS_PORT` | Redis port | `6379` |
| `VAPID_PUBLIC_KEY` | WebPush public key | (optional) |
| `VAPID_PRIVATE_KEY` | WebPush private key | (optional) |

## Acknowledgments

- [Django Channels Documentation](https://channels.readthedocs.io/)
- [Redis Documentation](https://redis.io/documentation)
- [Bootstrap](https://getbootstrap.com/)
- [Django Allauth](https://django-allauth.readthedocs.io/)
