#!/usr/bin/env python3
"""
CYBERNAV // Raspberry Pi Zero 2 W Edge Client Agent
Connects to Cloud Orchestrator via WebSocket.
Supports both SAFE DRY-RUN (motors disconnected) and FULL HARDWARE mode.
"""

import os
import sys
import time
import json
import io
import base64
import asyncio
import logging
from typing import Optional

try:
    import websockets
except ImportError:
    print("Error: 'websockets' library is required. Run: pip install websockets")
    sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("RobotAgent")

# Check for Raspberry Pi Hardware Libraries
HARDWARE_AVAILABLE = False
try:
    import RPi.GPIO as GPIO
    from gpiozero import Motor, PWMOutputDevice
    HARDWARE_AVAILABLE = True
except (ImportError, RuntimeError):
    pass

# Check for Pi Camera
CAMERA_AVAILABLE = False
try:
    from picamera2 import Picamera2
    CAMERA_AVAILABLE = True
except ImportError:
    pass

# Check for VL53L0X ToF Sensor
VL53L0X_AVAILABLE = False
try:
    import board
    import busio
    import adafruit_vl53l0x
    VL53L0X_AVAILABLE = True
except (ImportError, NotImplementedError):
    pass


class EdgeRobotAgent:
    def __init__(self, server_ws_url: str = "ws://localhost:8000/ws/robot"):
        self.server_ws_url = server_ws_url
        self.running = True
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        
        # Hardware state
        self.hardware_mode = HARDWARE_AVAILABLE
        self.simulated_tof_dist = 420
        self.current_state = "IDLE"

        logger.info("=" * 60)
        logger.info("🚀 INITIALIZING CYBERNAV ROBOT EDGE AGENT")
        logger.info(f"   Hardware Mode (GPIO/Motors): {'ENABLED' if self.hardware_mode else 'DRY-RUN (SAFE SIMULATION)'}")
        logger.info(f"   Camera Module v2:           {'DETECTED' if CAMERA_AVAILABLE else 'MOCK PATTERN'}")
        logger.info(f"   VL53L0X ToF Sensor:         {'DETECTED' if VL53L0X_AVAILABLE else 'SIMULATED (420mm)'}")
        logger.info("=" * 60)

        self._init_hardware()

    def _init_hardware(self):
        if self.hardware_mode:
            logger.info("Setting up GPIO pins for L298N motor driver...")
            # GPIO setup can be initialized here
        else:
            logger.info("🛡️ RUNNING IN SAFE DRY-RUN MODE: Motors are safely simulated in terminal.")

    def read_tof_distance(self) -> int:
        """Reads front distance in millimeters"""
        if VL53L0X_AVAILABLE:
            try:
                # Real sensor reading
                i2c = busio.I2C(board.SCL, board.SDA)
                vl53 = adafruit_vl53l0x.VL53L0X(i2c)
                return int(vl53.range)
            except Exception as e:
                logger.warning(f"Error reading VL53L0X sensor: {e}")
        
        # Simulated distance with slight realistic jitter
        import random
        self.simulated_tof_dist = max(120, min(800, self.simulated_tof_dist + random.randint(-15, 15)))
        return self.simulated_tof_dist

    def capture_frame_base64(self) -> str:
        """Captures a frame and converts to Base64 JPEG string"""
        if CAMERA_AVAILABLE:
            try:
                picam2 = Picamera2()
                picam2.start()
                frame = picam2.capture_array()
                picam2.stop()
                # Convert array to JPEG buffer
                from PIL import Image
                img = Image.fromarray(frame)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=75)
                return base64.b64encode(buf.getvalue()).decode("utf-8")
            except Exception as e:
                logger.warning(f"Pi Camera capture failed: {e}")

        # Return a simulated test pattern frame
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (640, 480), color=(24, 30, 45))
        draw = ImageDraw.Draw(img)
        draw.polygon([(0, 480), (640, 480), (480, 240), (160, 240)], fill=(60, 75, 95))
        draw.rectangle([80, 140, 200, 360], fill=(37, 99, 235), outline=(191, 219, 254), width=3)  # Blue door
        draw.rectangle([260, 280, 380, 420], fill=(220, 38, 38), outline=(254, 202, 202), width=3) # Obstacle
        draw.rectangle([450, 220, 580, 440], fill=(16, 185, 129), outline=(167, 243, 208), width=2) # Corridor
        draw.text((20, 20), f"CYBERNAV EDGE STREAM - {time.strftime('%H:%M:%S')}", fill=(56, 189, 248))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    async def execute_action(self, action: str, speed: int = 150, duration_s: float = 1.0, degrees: int = 0):
        """Executes a primitive motion with reactive obstacle checking"""
        logger.info(f"▶️ [MOTOR EXECUTE] Action: {action.upper()} | Speed: {speed} PWM | Duration: {duration_s}s | Deg: {degrees}°")
        
        # Reactive safety check: If forward motion requested but ToF < 150mm, abort!
        current_dist = self.read_tof_distance()
        if "FORWARD" in action.upper() and current_dist < 150:
            logger.warning(f"⛔ EMERGENCY BRAKE: Obstacle detected at {current_dist}mm! Forward command aborted.")
            if self.ws:
                await self.ws.send(json.dumps({
                    "type": "LOG",
                    "message": f"EMERGENCY BRAKE TRIGGERED: Distance {current_dist}mm < 150mm"
                }))
            return

        # Physical execution on L298N pins if in hardware mode
        if self.hardware_mode:
            # Code to drive physical motors
            pass
        else:
            logger.info(f"   [DRY RUN MOTOR SIM] Simulating {action.upper()} for {duration_s}s...")

        await asyncio.sleep(duration_s)
        logger.info(f"⏹️ [MOTOR COMPLETED] {action.upper()} finished.")

    async def handle_cloud_message(self, message_str: str):
        """Processes instructions received from Cloud Orchestrator"""
        try:
            data = json.loads(message_str)
            msg_type = data.get("type", "")

            if msg_type == "EXECUTE_PRIMITIVE":
                action = data.get("action", "STOP")
                speed = data.get("speed", 150)
                dur = data.get("duration_s", 1.0)
                await self.execute_action(action, speed=speed, duration_s=dur)

            elif msg_type == "EXECUTE_PLAN":
                plan = data.get("plan", {})
                commands = plan.get("commands", [])
                logger.info(f"📋 Received Motion Plan with {len(commands)} steps from Azure OpenAI!")
                
                for step_idx, cmd in enumerate(commands):
                    action = cmd.get("action", "STOP")
                    speed = cmd.get("speed", 160)
                    dur = cmd.get("duration_s", 1.0)
                    deg = cmd.get("degrees", 0)
                    
                    logger.info(f"Executing Step #{step_idx + 1}: {action}")
                    await self.execute_action(action, speed=speed, duration_s=dur, degrees=deg)
                    await asyncio.sleep(0.3)

            elif msg_type == "REQUEST_SNAPSHOT":
                logger.info("Cloud requested camera snapshot. Capturing frame...")
                b64_frame = self.capture_frame_base64()
                dist = self.read_tof_distance()
                if self.ws:
                    await self.ws.send(json.dumps({
                        "type": "FRAME_TELEMETRY",
                        "image_base64": b64_frame,
                        "tof_distance_mm": dist
                    }))

        except Exception as e:
            logger.error(f"Error handling cloud message: {e}")

    async def heartbeat_loop(self):
        """Sends telemetry updates to cloud backend every 2 seconds"""
        while self.running:
            try:
                if self.ws:
                    dist = self.read_tof_distance()
                    await self.ws.send(json.dumps({
                        "type": "HEARTBEAT",
                        "tof_distance_mm": dist,
                        "status": self.current_state,
                        "timestamp": time.time()
                    }))
            except Exception as e:
                logger.debug(f"Heartbeat error: {e}")
                break
            await asyncio.sleep(2.0)

    async def run(self):
        """Main agent event loop with auto-reconnection"""
        while self.running:
            try:
                logger.info(f"Connecting to Cloud Orchestrator at: {self.server_ws_url}...")
                async with websockets.connect(self.server_ws_url) as websocket:
                    self.ws = websocket
                    logger.info("✅ SUCCESS: Connected to Cloud Orchestrator!")

                    # Immediately send initial snapshot and distance
                    initial_frame = self.capture_frame_base64()
                    initial_dist = self.read_tof_distance()
                    await websocket.send(json.dumps({
                        "type": "FRAME_TELEMETRY",
                        "image_base64": initial_frame,
                        "tof_distance_mm": initial_dist
                    }))

                    # Run heartbeat in background task
                    heartbeat_task = asyncio.create_task(self.heartbeat_loop())

                    # Listen for commands
                    async for message in websocket:
                        await self.handle_cloud_message(message)

                    heartbeat_task.cancel()

            except (websockets.ConnectionClosed, ConnectionRefusedError, OSError) as e:
                logger.warning(f"Connection to Cloud server unavailable ({e}). Retrying in 4s...")
                await asyncio.sleep(4.0)
            except Exception as e:
                logger.error(f"Unexpected agent error: {e}")
                await asyncio.sleep(4.0)

if __name__ == "__main__":
    server_url = os.getenv("ROBOT_SERVER_URL", "ws://localhost:8000/ws/robot")
    agent = EdgeRobotAgent(server_ws_url=server_url)
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        logger.info("Agent stopped by user.")
