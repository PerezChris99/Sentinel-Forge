"""
WebSocket server for real-time updates using Socket.IO
"""
import os
import logging
from datetime import datetime
from typing import Dict, Set
import socketio
from fastapi import FastAPI
from jose import JWTError, jwt
import redis.asyncio as redis

logger = logging.getLogger(__name__)

# Resolve allowed origins for Socket.IO
_cors_env = os.getenv("CORS_ORIGINS", "*")
if _cors_env.strip() == "*":
    _ws_cors = '*'
else:
    _ws_cors = [o.strip() for o in _cors_env.split(",") if o.strip()]

# Create Socket.IO server with CORS
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=_ws_cors,
    logger=True,
    engineio_logger=True
)

# Connected clients registry
connected_clients: Set[str] = set()
user_rooms: Dict[str, Set[str]] = {}  # user_id -> set of socket ids
socket_users: Dict[str, str] = {}  # socket id -> authenticated user id


class WebSocketManager:
    """Manages WebSocket connections and broadcasts"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.sio = sio
    
    async def broadcast_alert(self, alert_data: dict):
        """Broadcast new alert to all connected clients"""
        await self.sio.emit('new_alert', alert_data)
        logger.info(f"Broadcasted alert: {alert_data.get('id')}")
    
    async def broadcast_sighting(self, sighting_data: dict):
        """Broadcast new sighting to all connected clients"""
        await self.sio.emit('new_sighting', sighting_data)
        logger.info(f"Broadcasted sighting: {sighting_data.get('id')}")
    
    async def send_camera_status(self, camera_id: str, status: str):
        """Send camera status update"""
        await self.sio.emit('camera_status', {
            'camera_id': camera_id,
            'status': status,
            'timestamp': str(datetime.utcnow().isoformat())
        })
    
    async def send_to_user(self, user_id: str, event: str, data: dict):
        """Send event to specific user"""
        if user_id in user_rooms:
            await self.sio.emit(event, data, room=user_id)

    async def broadcast_behavior_event(self, event_data: dict):
        """Broadcast behavior analysis event (loitering, intrusion, etc.)"""
        await self.sio.emit('behavior_event', event_data)
        logger.info("Broadcasted behavior event: %s", event_data.get('behavior_type'))

    async def broadcast_vehicle_alert(self, vehicle_data: dict):
        """Broadcast vehicle intelligence alert (plate match, stolen, etc.)"""
        await self.sio.emit('vehicle_alert', vehicle_data)
        logger.info("Broadcasted vehicle alert: %s", vehicle_data.get('plate_text'))

    async def broadcast_zone_update(self, zone_data: dict):
        """Broadcast zone occupancy or status change"""
        await self.sio.emit('zone_update', zone_data)

    async def broadcast_heatmap(self, heatmap_data: dict):
        """Broadcast live heatmap data"""
        await self.sio.emit('heatmap_update', heatmap_data)


# Socket.IO event handlers
@sio.event
async def connect(sid, environ, auth):
    """Authenticate Socket.IO clients before accepting the connection."""
    environment = os.getenv("SENTINELFORGE_ENV", os.getenv("ENVIRONMENT", "development")).lower()
    token = auth.get("token") if isinstance(auth, dict) else None
    if not token:
        header = environ.get("HTTP_AUTHORIZATION", "")
        if header.lower().startswith("bearer "):
            token = header[7:].strip()
    user_id = None
    secret = os.getenv("SECRET_KEY", "")
    if token and secret:
        try:
            payload = jwt.decode(token, secret, algorithms=["HS256"], audience="sentinelforge-api", issuer="sentinelforge")
            user_id = payload.get("sub")
        except JWTError:
            user_id = None
    if environment in {"production", "prod"} and not user_id:
        logger.warning("Rejected unauthenticated Socket.IO connection: %s", sid)
        return False
    connected_clients.add(sid)
    if user_id:
        socket_users[sid] = str(user_id)
    await sio.emit("connection_established", {
        "sid": sid, "authenticated": bool(user_id), "timestamp": datetime.utcnow().isoformat()
    }, room=sid)


@sio.event
async def disconnect(sid):
    """Handle client disconnection"""
    connected_clients.discard(sid)
    authenticated_user = socket_users.pop(sid, None)
    if authenticated_user and authenticated_user in user_rooms:
        user_rooms[authenticated_user].discard(sid)
        if not user_rooms[authenticated_user]:
            user_rooms.pop(authenticated_user, None)
    for rooms in user_rooms.values():
        rooms.discard(sid)
    logger.info("Client disconnected: %s", sid)


@sio.event
async def subscribe(sid, data):
    """Subscribe to specific events"""
    channel = data.get("channel")
    requested_user = data.get("user_id")
    authenticated_user = socket_users.get(sid)
    if requested_user and requested_user != authenticated_user:
        await sio.emit("error", {"detail": "Cannot subscribe to another user's room"}, room=sid)
        return
    user_id = authenticated_user
    if user_id:
        user_rooms.setdefault(user_id, set()).add(sid)
        sio.enter_room(sid, user_id)
    if channel:
        sio.enter_room(sid, channel)
    await sio.emit("subscribed", {"channel": channel, "user_id": user_id}, room=sid)
    
    logger.info(f"Client {sid} subscribed to channel: {channel}, user: {user_id}")


@sio.event
async def unsubscribe(sid, data):
    """Unsubscribe from specific events"""
    channel = data.get("channel")
    user_id = socket_users.get(sid)
    if channel:
        sio.leave_room(sid, channel)
    if user_id and user_id in user_rooms:
        user_rooms[user_id].discard(sid)
        sio.leave_room(sid, user_id)
    await sio.emit("unsubscribed", {"channel": channel, "user_id": user_id}, room=sid)


@sio.event
async def ping(sid):
    """Health check / keep-alive"""
    await sio.emit('pong', room=sid)


@sio.event
async def acknowledge_alert(sid, data):
    """Handle alert acknowledgment from client"""
    alert_id = data.get('alert_id')
    user_id = socket_users.get(sid)
    
    # Broadcast acknowledgment to other users
    await sio.emit('alert_acknowledged', {
        'alert_id': alert_id,
        'acknowledged_by': user_id,
        'timestamp': str(datetime.utcnow().isoformat())
    }, skip_sid=sid)


# Attach Socket.IO to FastAPI app
def attach_socketio(app: FastAPI):
    """Attach Socket.IO to FastAPI app"""
    socket_app = socketio.ASGIApp(
        sio,
        app,
        socketio_path='/ws/socket.io'
    )
    return socket_app


# Export
__all__ = ['sio', 'WebSocketManager', 'attach_socketio']
