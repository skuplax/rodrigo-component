from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Depends
from pydantic import BaseModel
from contextlib import asynccontextmanager
from typing import Optional, List
from datetime import datetime
import asyncio
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import select, desc, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

# Load environment variables from .env file
load_dotenv()

from gpio import JukeboxState, GPIOMonitor
from player import PlayerService
from dashboard.routes import router as dashboard_router
from db.database import get_db
from db.models import Log, Source, AppState

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set GPIO Monitor logger to WARNING level
logging.getLogger("gpio").setLevel(logging.WARNING)

# Global state, player service, and monitor
jukebox_state = JukeboxState()
player_service: Optional[PlayerService] = None
gpio_monitor: Optional[GPIOMonitor] = None


def is_development_mode() -> bool:
    """
    Detect if running in development mode or stdout mode.
    Returns True if:
    - stdout is a TTY (interactive terminal)
    - ENV environment variable is set to 'development' or 'dev'
    - DEV or DEVELOPMENT environment variables are set to 'true' or '1'
    """
    # Check environment variables
    env = os.getenv('ENV', '').lower()
    dev = os.getenv('DEV', '').lower()
    development = os.getenv('DEVELOPMENT', '').lower()
    
    if env in ('development', 'dev') or dev in ('true', '1') or development in ('true', '1'):
        return True
    
    # Check if stdout is a TTY (interactive terminal)
    if sys.stdout.isatty():
        return True
    
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown"""
    # Startup
    global player_service, gpio_monitor
    logger.info("Starting Rodrigo Component...")
    
    # Configure voice model path
    project_root = Path(__file__).parent
    voice_model_path = os.getenv(
        'PIPER_VOICE_MODEL',
        str(project_root / "data" / "piper" / "voices" / "en_US-lessac-medium.onnx")
    )

    # Check if voice model exists
    if not Path(voice_model_path).exists():
        logger.warning(f"Voice model not found at {voice_model_path}, announcements will be disabled")
        voice_model_path = None
    
    # Initialize player service (it loads sources and watched videos from DB internally)
    is_dev = is_development_mode()
    player_service = PlayerService(
        jukebox_state,
        announcement_voice_model=voice_model_path,
        dev_mode=is_dev
    )
    
    # Start Mopidy thread
    player_service.start()
    
    # Initialize GPIO monitor with player service
    gpio_monitor = GPIOMonitor(jukebox_state, player_service)
    gpio_monitor.start()
    
    logger.info("Rodrigo Component started successfully")
    
    # Only announce startup if not in development mode
    if is_dev:
        logger.info("Development mode detected - skipping startup announcement")
    else:
        # Wait a moment for threads to be ready, then announce startup
        await asyncio.sleep(2.0)
        if player_service:
            player_service.announce_startup()
    
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

# Include dashboard router
app.include_router(dashboard_router)


class AnnouncementRequest(BaseModel):
    """Request model for announcement endpoint"""
    text: str


@app.get("/root")
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
            "announce": "/api/announce",
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
    state = jukebox_state.get_state()
    
    # Add source name and type from player_service if available
    if player_service:
        try:
            current_source_obj = player_service.source_manager.get_current_source()
            if current_source_obj:
                state["current_source_name"] = current_source_obj.name
                state["current_source_type"] = current_source_obj.source_type  # 'music' or 'news'
            else:
                state["current_source_name"] = None
                state["current_source_type"] = None
        except Exception as e:
            logger.debug(f"Could not get source info: {e}")
            state["current_source_name"] = None
            state["current_source_type"] = None
    else:
        state["current_source_name"] = None
        state["current_source_type"] = None
    
    return state


@app.get("/api/sources")
async def get_sources(db: AsyncSession = Depends(get_db)):
    """Get all sources and current source index"""
    try:
        # Get all sources
        result = await db.execute(select(Source).order_by(Source.created_at))
        sources = result.scalars().all()
        
        # Get current source index
        current_index = 0
        if player_service:
            current_index = player_service.source_manager.current_source_index
        else:
            # Try to get from database
            app_state_result = await db.execute(
                select(AppState).where(AppState.key == 'current_source_index')
            )
            app_state = app_state_result.scalar_one_or_none()
            if app_state and app_state.value:
                try:
                    current_index = int(app_state.value)
                except (ValueError, TypeError):
                    current_index = 0
        
        # Convert sources to dict format
        sources_data = [
            {
                "id": str(source.id),
                "type": source.type,
                "name": source.name,
                "uri": source.uri,
                "source_type": source.source_type,
                "created_at": source.created_at.isoformat() if source.created_at else None
            }
            for source in sources
        ]
        
        return {
            "sources": sources_data,
            "current_index": current_index,
            "total": len(sources_data)
        }
    except Exception as e:
        logger.error(f"Error fetching sources: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch sources: {str(e)}")


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


@app.post("/api/announce")
async def announce(request: AnnouncementRequest):
    """
    Trigger a custom announcement
    
    Args:
        request: AnnouncementRequest with text to announce
        
    Example:
        curl -X POST http://localhost:8000/api/announce -H "Content-Type: application/json" -d '{"text": "Hello, this is a test"}'
    """
    if not player_service:
        raise HTTPException(status_code=503, detail="Player service not initialized")
    
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    
    try:
        from player.announcement_thread import AnnouncementCommand, AnnouncementCommandType
        
        command = AnnouncementCommand(
            AnnouncementCommandType.ANNOUNCE,
            {"text": request.text}
        )
        player_service.announcement_thread.send_command(command)
        
        logger.info(f"Announcement requested: '{request.text}'")
        return {
            "status": "success",
            "message": "Announcement queued",
            "text": request.text
        }
    except Exception as e:
        logger.error(f"Error sending announcement: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send announcement: {str(e)}")


@app.post("/api/player/play-pause")
async def play_pause():
    """Toggle play/pause"""
    if not player_service:
        raise HTTPException(status_code=503, detail="Player service not initialized")
    
    try:
        player_service.toggle_play()
        current_state = jukebox_state.get_state()
        logger.info("Play/pause toggled via API")
        return {
            "status": "success",
            "message": "Play/pause toggled",
            "state": current_state
        }
    except Exception as e:
        logger.error(f"Error toggling play/pause: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to toggle play/pause: {str(e)}")


@app.post("/api/player/next")
async def next_track():
    """Skip to next track"""
    if not player_service:
        raise HTTPException(status_code=503, detail="Player service not initialized")
    
    try:
        player_service.next()
        current_state = jukebox_state.get_state()
        logger.info("Next track requested via API")
        return {
            "status": "success",
            "message": "Skipped to next track",
            "state": current_state
        }
    except Exception as e:
        logger.error(f"Error skipping to next track: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to skip to next track: {str(e)}")


@app.post("/api/player/previous")
async def previous_track():
    """Go to previous track"""
    if not player_service:
        raise HTTPException(status_code=503, detail="Player service not initialized")
    
    try:
        player_service.previous()
        current_state = jukebox_state.get_state()
        logger.info("Previous track requested via API")
        return {
            "status": "success",
            "message": "Went to previous track",
            "state": current_state
        }
    except Exception as e:
        logger.error(f"Error going to previous track: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to go to previous track: {str(e)}")


@app.post("/api/player/cycle-source")
async def cycle_source():
    """Cycle to next source"""
    if not player_service:
        raise HTTPException(status_code=503, detail="Player service not initialized")
    
    try:
        player_service.cycle_source()
        current_state = jukebox_state.get_state()
        logger.info("Source cycled via API")
        return {
            "status": "success",
            "message": "Source cycled",
            "state": current_state
        }
    except Exception as e:
        logger.error(f"Error cycling source: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cycle source: {str(e)}")


@app.get("/api/logs")
async def get_logs(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    level: Optional[str] = Query(None, description="Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"),
    module: Optional[str] = Query(None, description="Filter by module name"),
    search: Optional[str] = Query(None, description="Search in message text"),
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    db: AsyncSession = Depends(get_db)
):
    """Get logs from database with filtering"""
    try:
        # Build query
        query = select(Log).order_by(desc(Log.timestamp))
        
        # Apply filters
        conditions = []
        
        if level:
            conditions.append(Log.level == level.upper())
        
        if module:
            conditions.append(or_(
                Log.module.ilike(f"%{module}%"),
                Log.logger_name.ilike(f"%{module}%")
            ))
        
        if search:
            conditions.append(or_(
                Log.message.ilike(f"%{search}%"),
                Log.exception_info.ilike(f"%{search}%")
            ))
        
        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                conditions.append(Log.timestamp >= start_dt)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format. Use ISO format.")
        
        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                conditions.append(Log.timestamp <= end_dt)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date format. Use ISO format.")
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # Get total count for pagination
        count_query = select(func.count()).select_from(Log)
        if conditions:
            count_query = count_query.where(and_(*conditions))
        total_result = await db.execute(count_query)
        total = total_result.scalar()
        
        # Apply pagination
        query = query.limit(limit).offset(offset)
        
        # Execute query
        result = await db.execute(query)
        logs = result.scalars().all()
        
        # Convert to dict format
        logs_data = [
            {
                "id": str(log.id),
                "level": log.level,
                "logger_name": log.logger_name,
                "message": log.message,
                "module": log.module,
                "function": log.function,
                "line_number": log.line_number,
                "exception_info": log.exception_info,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                "extra_data": log.extra_data
            }
            for log in logs
        ]
        
        return {
            "logs": logs_data,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error fetching logs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch logs: {str(e)}")


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


@app.get("/{path:path}")
async def catch_all(path: str):
    """Catch-all for undefined routes - must be last"""
    raise HTTPException(status_code=404, detail=f"Route /{path} not found")
