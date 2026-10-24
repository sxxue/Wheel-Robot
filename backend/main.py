import io
import time
import json
import base64
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image, ImageDraw

from backend.config import settings
from backend.services.som_service import som_service
from backend.services.azure_openai import azure_openai_service
from backend.services.azure_speech import azure_speech_service
from backend.services.gemini_service import gemini_service

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FYP2Backend")

app = FastAPI(
    title="Cloud-Assisted Wheeled Robot Orchestrator",
    description="FYP2 Cloud Backend connecting Web Dashboard, Azure AI Services, and Raspberry Pi Edge Robot",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for dashboard
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# In-Memory State
class SystemState:
    robot_connected: bool = False
    robot_websocket: Optional[WebSocket] = None
    dashboard_websockets: List[WebSocket] = []
    
    last_tof_distance_mm: int = 420
    last_robot_heartbeat: float = 0.0
    
    # Store latest raw and annotated images as Base64 Data URIs
    raw_image_data_uri: Optional[str] = None
    som_image_data_uri: Optional[str] = None
    detected_marks: List[Dict[str, Any]] = []
    
    latest_plan: Optional[Dict[str, Any]] = None
    execution_logs: List[Dict[str, Any]] = []

state = SystemState()

from backend.services.scene_generator import render_multi_object_scene, get_default_detected_objects

# Generate a default initial test scene with multiple salient objects
def generate_initial_test_scene():
    raw_bytes = render_multi_object_scene(640, 480, timestamp_text=f"CYBERNAV SCENE BENCHMARK - {time.strftime('%H:%M:%S')}")
    annotated_bytes, marks = som_service.annotate_frame(raw_bytes)
    state.raw_image_data_uri = som_service.bytes_to_base64_data_uri(raw_bytes)
    state.som_image_data_uri = som_service.bytes_to_base64_data_uri(annotated_bytes)
    state.detected_marks = marks

generate_initial_test_scene()

async def broadcast_to_dashboards(message: dict):
    """Broadcast real-time status update to all open Web Dashboards"""
    disconnected = []
    for ws in state.dashboard_websockets:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in state.dashboard_websockets:
            state.dashboard_websockets.remove(ws)

# Models
class NaturalLanguageCommandRequest(BaseModel):
    command: str
    tof_distance_mm: Optional[int] = None

class TestMotorRequest(BaseModel):
    action: str  # FORWARD, BACKWARD, TURN_LEFT, TURN_RIGHT, STOP
    speed: int = 150
    duration_s: float = 1.0

# ----------------- REST Endpoints ----------------- #

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>Dashboard index.html not yet created</h1>")

@app.get("/api/status")
async def get_system_status():
    is_robot_alive = state.robot_connected and (time.time() - state.last_robot_heartbeat < 10)
    
    if settings.AI_PROVIDER == "gemini":
        ai_status = "Ready (Google Gemini 1.5 Flash)" if gemini_service.is_ready else "Ready (Gemini Simulation)"
    else:
        ai_status = "Ready (Mock)" if settings.USE_MOCK_AZURE else "Ready (Azure OpenAI GPT-4o)"

    return {
        "status": "online",
        "robot": {
            "connected": is_robot_alive,
            "last_heartbeat": state.last_robot_heartbeat,
            "tof_distance_mm": state.last_tof_distance_mm
        },
        "ai": {
            "provider": settings.AI_PROVIDER,
            "status": ai_status
        },
        "azure": {
            "use_mock": settings.USE_MOCK_AZURE,
            "openai_status": ai_status,
            "speech_status": azure_speech_service.get_speech_config()["status"]
        },
        "vision": {
            "has_raw_image": bool(state.raw_image_data_uri),
            "has_som_image": bool(state.som_image_data_uri),
            "marks_count": len(state.detected_marks)
        }
    }

@app.post("/api/command")
async def process_natural_language_command(req: NaturalLanguageCommandRequest):
    """
    Core natural language pipeline:
    1. Reads user prompt (e.g. 'avoid the obstacle and reach the blue door')
    2. Takes current VL53L0X distance reading
    3. Feeds SoM annotated scene + distance + command to Azure OpenAI (GPT-4o)
    4. Receives deterministic motion plan
    5. Transmits plan to robot via WebSocket
    """
    tof_dist = req.tof_distance_mm if req.tof_distance_mm is not None else state.last_tof_distance_mm
    logger.info(f"Received Natural Language Command: '{req.command}' (ToF: {tof_dist}mm)")

    # 1. Run Multimodal Reasoning (Gemini or Azure OpenAI)
    if settings.AI_PROVIDER == "gemini":
        plan = await gemini_service.plan_navigation(
            command_text=req.command,
            tof_distance_mm=tof_dist,
            som_metadata=state.detected_marks,
            image_data_uri=state.som_image_data_uri
        )
    else:
        plan = await azure_openai_service.plan_navigation(
            command_text=req.command,
            tof_distance_mm=tof_dist,
            som_metadata=state.detected_marks,
            image_data_uri=state.som_image_data_uri
        )
    state.latest_plan = plan

    # 2. Add log entry
    log_entry = {
        "timestamp": time.strftime("%H:%M:%S"),
        "command": req.command,
        "tof": tof_dist,
        "plan": plan
    }
    state.execution_logs.insert(0, log_entry)

    # 3. Transmit to Robot if connected
    dispatched_to_robot = False
    if state.robot_websocket and state.robot_connected:
        try:
            await state.robot_websocket.send_json({
                "type": "EXECUTE_PLAN",
                "plan": plan
            })
            dispatched_to_robot = True
            logger.info("Motion plan successfully dispatched to robot via WebSocket.")
        except Exception as e:
            logger.error(f"Failed to send plan to robot: {e}")

    # 4. Notify all dashboards
    await broadcast_to_dashboards({
        "type": "NEW_PLAN",
        "command": req.command,
        "plan": plan,
        "dispatched_to_robot": dispatched_to_robot
    })

    return {
        "status": "success",
        "dispatched_to_robot": dispatched_to_robot,
        "plan": plan
    }

@app.post("/api/upload-frame")
async def upload_camera_frame(
    file: UploadFile = File(...),
    tof_distance_mm: Optional[int] = Form(None)
):
    """Receives a camera snapshot from Raspberry Pi or test script, generates SoM annotation, and updates dashboard"""
    contents = await file.read()
    if tof_distance_mm is not None:
        state.last_tof_distance_mm = tof_distance_mm

    # Run SoM annotation
    annotated_bytes, marks = som_service.annotate_frame(contents)

    state.raw_image_data_uri = som_service.bytes_to_base64_data_uri(contents)
    state.som_image_data_uri = som_service.bytes_to_base64_data_uri(annotated_bytes)
    state.detected_marks = marks

    # Broadcast updated image to dashboards
    await broadcast_to_dashboards({
        "type": "IMAGE_UPDATE",
        "raw_image": state.raw_image_data_uri,
        "som_image": state.som_image_data_uri,
        "marks": state.detected_marks,
        "tof_distance_mm": state.last_tof_distance_mm
    })

    return {
        "status": "success",
        "marks_detected": len(marks),
        "tof_distance_mm": state.last_tof_distance_mm
    }

@app.post("/api/test-motor")
async def test_motor_manual(req: TestMotorRequest):
    """Sends a direct motor test primitive to the robot"""
    if not (state.robot_websocket and state.robot_connected):
        return JSONResponse(status_code=400, content={"status": "error", "message": "Robot is not connected."})

    command_payload = {
        "type": "EXECUTE_PRIMITIVE",
        "action": req.action,
        "speed": req.speed,
        "duration_s": req.duration_s
    }

    try:
        await state.robot_websocket.send_json(command_payload)
        return {"status": "success", "message": f"Sent {req.action} command to robot"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# ----------------- WebSocket Endpoints ----------------- #

@app.websocket("/ws/robot")
async def websocket_robot_endpoint(websocket: WebSocket):
    """
    WebSocket channel for the Raspberry Pi Zero 2 W agent.
    Receives telemetry, distance readings, and dispatches movement commands.
    """
    await websocket.accept()
    state.robot_websocket = websocket
    state.robot_connected = True
    state.last_robot_heartbeat = time.time()
    logger.info("🟢 Raspberry Pi Edge Robot connected via WebSocket!")

    await broadcast_to_dashboards({
        "type": "ROBOT_STATUS",
        "connected": True,
        "message": "Raspberry Pi connected successfully"
    })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "HEARTBEAT":
                state.last_robot_heartbeat = time.time()
                if "tof_distance_mm" in data:
                    state.last_tof_distance_mm = int(data["tof_distance_mm"])
                
                await broadcast_to_dashboards({
                    "type": "TELEMETRY",
                    "tof_distance_mm": state.last_tof_distance_mm,
                    "battery_voltage": data.get("battery_voltage", "N/A"),
                    "status": data.get("status", "IDLE")
                })

            elif msg_type == "FRAME_TELEMETRY":
                # Pi sent Base64 image
                raw_b64 = data.get("image_base64", "")
                if raw_b64:
                    raw_bytes = io.BytesIO(base64.b64decode(raw_b64)).getvalue()
                    annotated_bytes, marks = som_service.annotate_frame(raw_bytes)
                    state.raw_image_data_uri = som_service.bytes_to_base64_data_uri(raw_bytes)
                    state.som_image_data_uri = som_service.bytes_to_base64_data_uri(annotated_bytes)
                    state.detected_marks = marks
                    if "tof_distance_mm" in data:
                        state.last_tof_distance_mm = int(data["tof_distance_mm"])

                    await broadcast_to_dashboards({
                        "type": "IMAGE_UPDATE",
                        "raw_image": state.raw_image_data_uri,
                        "som_image": state.som_image_data_uri,
                        "marks": state.detected_marks,
                        "tof_distance_mm": state.last_tof_distance_mm
                    })

            elif msg_type == "LOG":
                logger.info(f"[ROBOT LOG] {data.get('message')}")
                await broadcast_to_dashboards({
                    "type": "ROBOT_LOG",
                    "message": data.get("message")
                })

    except WebSocketDisconnect:
        logger.warning("🔴 Raspberry Pi disconnected from WebSocket.")
    except Exception as e:
        logger.error(f"WebSocket error on robot connection: {e}")
    finally:
        state.robot_connected = False
        state.robot_websocket = None
        await broadcast_to_dashboards({
            "type": "ROBOT_STATUS",
            "connected": False,
            "message": "Raspberry Pi disconnected"
        })

@app.websocket("/ws/dashboard")
async def websocket_dashboard_endpoint(websocket: WebSocket):
    """
    WebSocket channel for Web Dashboard clients.
    Streams real-time telemetry, logs, and vision updates.
    """
    await websocket.accept()
    state.dashboard_websockets.append(websocket)
    logger.info(f"Dashboard client connected. Active dashboard clients: {len(state.dashboard_websockets)}")

    if settings.AI_PROVIDER == "gemini":
        ai_display_status = "AI: GEMINI 3.8 FLASH" if gemini_service.is_ready else "AI: GEMINI (SIMULATION)"
    else:
        ai_display_status = "AI: MOCK MODE" if settings.USE_MOCK_AZURE else "AI: GPT-4o ACTIVE"

    # Send initial full state
    is_robot_alive = state.robot_connected and (time.time() - state.last_robot_heartbeat < 10)
    await websocket.send_json({
        "type": "INITIAL_STATE",
        "robot_connected": is_robot_alive,
        "tof_distance_mm": state.last_tof_distance_mm,
        "raw_image": state.raw_image_data_uri,
        "som_image": state.som_image_data_uri,
        "marks": state.detected_marks,
        "latest_plan": state.latest_plan,
        "execution_logs": state.execution_logs[:5],
        "ai_config": {
            "provider": settings.AI_PROVIDER,
            "status_text": ai_display_status,
            "is_active": True
        }
    })

    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in state.dashboard_websockets:
            state.dashboard_websockets.remove(websocket)
        logger.info("Dashboard client disconnected.")
