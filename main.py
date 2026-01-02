from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager
from typing import Optional
import asyncio
import logging

from gpio import JukeboxState, GPIOMonitor
from player import PlayerService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set GPIO Monitor logger to WARNING level
logging.getLogger("gpio").setLevel(logging.WARNING)

# Global state, player service, and monitor
jukebox_state = JukeboxState()
player_service: Optional[PlayerService] = None
gpio_monitor: Optional[GPIOMonitor] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown"""
    # Startup
    global player_service, gpio_monitor
    logger.info("Starting Rodrigo Component...")
    
    # Initialize player service (includes MopidyThread, but not started yet)
    # Sources default to SourceManager defaults if not provided
    player_service = PlayerService(jukebox_state)
    
    # Start Mopidy thread
    player_service.start()
    
    # Initialize GPIO monitor with player service
    gpio_monitor = GPIOMonitor(jukebox_state, player_service)
    gpio_monitor.start()
    
    logger.info("Rodrigo Component started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Rodrigo Component...")
    
    # Stop GPIO monitor
    if gpio_monitor:
        gpio_monitor.stop()
    
    # Stop Mopidy thread
    if player_service:
        player_service.stop()
    
    logger.info("Rodrigo Component stopped")


app = FastAPI(
    title="Rodrigo Component",
    description="GPIO Jukebox with Monitoring Dashboard",
    version="0.1.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "name": "Rodrigo Component",
        "description": "GPIO Jukebox with Monitoring Dashboard",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "state": "/api/state",
            "gpio_events": "/api/gpio/events",
            "gpio_status": "/api/gpio/status",
            "websocket": "/ws/gpio"
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "gpio_monitor": "running" if gpio_monitor and gpio_monitor.running else "stopped"
    }


@app.get("/api/state")
async def get_state():
    """Get current jukebox state"""
    return jukebox_state.get_state()


@app.get("/api/gpio/events")
async def get_gpio_events(limit: int = 10):
    """Get recent GPIO button events"""
    return {
        "events": jukebox_state.get_recent_events(limit),
        "total_events": len(jukebox_state.button_events)
    }


@app.get("/api/gpio/status")
async def get_gpio_status():
    """Get current GPIO pin states"""
    return {
        "gpio_status": jukebox_state.gpio_status,
        "monitor_running": gpio_monitor.running if gpio_monitor else False
    }


@app.websocket("/ws/gpio")
async def websocket_gpio(websocket: WebSocket):
    """WebSocket endpoint for real-time GPIO event streaming"""
    await websocket.accept()
    logger.info("WebSocket client connected")
    
    try:
        last_event_count = 0
        while True:
            # Get current state
            current_events = jukebox_state.get_recent_events(10)
            current_state = jukebox_state.get_state()
            
            # Only send update if there are new events
            if len(current_events) != last_event_count:
                await websocket.send_json({
                    "type": "update",
                    "events": current_events,
                    "state": current_state
                })
                last_event_count = len(current_events)
            else:
                # Send heartbeat with state
                await websocket.send_json({
                    "type": "heartbeat",
                    "state": current_state
                })
            
            await asyncio.sleep(0.1)  # Update every 100ms
            
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
