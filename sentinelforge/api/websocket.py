"""
WebSocket server for real-time updates using Socket.IO
"""
import os
import logging
from datetime import datetime
from typing import Dict, Set
import socketio
from fastapi import FastAPI
import redis.asyncio as redis

logger = logging.getLogger(__name__)

# Create Socket.IO server with CORS
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',  # Restrict in production
    logger=True,
    engineio_logger=True
)

# Connected clients registry
connected_clients: Set[str] = set()
user_rooms: Dict[str, Set[str]] = {}  # user_id -> set of room names


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
        LOGGER.info("Broadcasted behavior event: %s", event_data.get('behavior_type'))

    async def broadcast_vehicle_alert(self, vehicle_data: dict):
        """Broadcast vehicle intelligence alert (plate match, stolen, etc.)"""
        await self.sio.emit('vehicle_alert', vehicle_data)
        LOGGER.info("Broadcasted vehicle alert: %s", vehicle_data.get('plate_text'))

    async def broadcast_zone_update(self, zone_data: dict):
        """Broadcast zone occupancy or status change"""
        await self.sio.emit('zone_update', zone_data)

    async def broadcast_heatmap(self, heatmap_data: dict):
        """Broadcast live heatmap data"""
        await self.sio.emit('heatmap_update', heatmap_data)


# Socket.IO event handlers
@sio.event
async def connect(sid, environ, auth):
    """Handle client connection"""
    connected_clients.add(sid)
    logger.info(f"Client connected: {sid}")
    
    # Send connection confirmation
    await sio.emit('connection_established', {
        'sid': sid,
        'timestamp': str(datetime.utcnow().isoformat())
    }, room=sid)


@sio.event
async def disconnect(sid):
    """Handle client disconnection"""
    connected_clients.discard(sid)
    
    # Remove from all rooms
    for user_id, rooms in user_rooms.items():
        rooms.discard(sid)
    
    logger.info(f"Client disconnected: {sid}")


@sio.event
async def subscribe(sid, data):
    """Subscribe to specific events"""
    channel = data.get('channel')
    user_id = data.get('user_id')
    
    if user_id:
        if user_id not in user_rooms:
            user_rooms[user_id] = set()
        user_rooms[user_id].add(sid)
        sio.enter_room(sid, user_id)
    
    if channel:
        sio.enter_room(sid, channel)
    
    await sio.emit('subscribed', {
        'channel': channel,
        'user_id': user_id
    }, room=sid)
    
    logger.info(f"Client {sid} subscribed to channel: {channel}, user: {user_id}")


@sio.event
async def unsubscribe(sid, data):
    """Unsubscribe from specific events"""
    channel = data.get('channel')
    user_id = data.get('user_id')
    
    if channel:
        sio.leave_room(sid, channel)
    
    if user_id and user_id in user_rooms:
        user_rooms[user_id].discard(sid)
        sio.leave_room(sid, user_id)
    
    await sio.emit('unsubscribed', {
        'channel': channel,
        'user_id': user_id
    }, room=sid)


@sio.event
async def ping(sid):
    """Health check / keep-alive"""
    await sio.emit('pong', room=sid)


@sio.event
async def acknowledge_alert(sid, data):
    """Handle alert acknowledgment from client"""
    alert_id = data.get('alert_id')
    user_id = data.get('user_id')
    
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
