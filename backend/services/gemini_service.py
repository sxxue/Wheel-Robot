import os
import json
import base64
import logging
import asyncio
from typing import Dict, Any, List
from PIL import Image
import io

from backend.config import settings

logger = logging.getLogger(__name__)

class GeminiReasoningService:
    """
    Google Gemini Multimodal Vision & Reasoning Service
    Uses Gemini (gemini-3.8-flash) to inspect Set-of-Mark (SoM) annotated scenes
    and output deterministic JSON navigation sequences for the wheeled robot.
    """

    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
        self.model_name = settings.GEMINI_MODEL or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        self.client = None
        self.is_ready = False

        self._initialize_client()

    def _initialize_client(self):
        if not self.api_key or self.api_key.startswith("your_gemini"):
            logger.info("Gemini API key not configured yet. Running in simulation fallback mode.")
            self.is_ready = False
            return

        try:
            # Prefer modern google.genai SDK
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
            self.is_ready = True
            logger.info(f"✅ Google Gemini Client (google.genai) initialized with model '{self.model_name}'!")
            return
        except ImportError:
            pass

        try:
            # Fallback to legacy google.generativeai
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(model_name=self.model_name)
            self.is_ready = True
            logger.info(f"✅ Google Gemini Model ({self.model_name}) initialized with google.generativeai!")
        except Exception as e:
            logger.warning(f"Failed to initialize Google Gemini client: {e}")
            self.is_ready = False

    async def plan_navigation(
        self,
        command_text: str,
        tof_distance_mm: int,
        som_metadata: List[Dict[str, Any]],
        image_data_uri: str = None
    ) -> Dict[str, Any]:
        """
        Sends the Set-of-Mark image, VL53L0X distance, and natural language command to Gemini.
        Returns a structured JSON motion plan.
        """
        if not self.is_ready:
            self.api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
            self.model_name = settings.GEMINI_MODEL or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
            self._initialize_client()

        if not self.is_ready:
            return self._mock_reasoning(command_text, tof_distance_mm, som_metadata)

        prompt = (
            "You are the high-level navigation planner for an autonomous 2WD wheeled robot equipped with a camera "
            "and a front Time-of-Flight (VL53L0X) distance sensor.\n\n"
            "The image attached contains numbered Set-of-Mark (SoM) badges [1], [2], [3] representing detected objects and corridors.\n"
            f"User Natural Language Command: '{command_text}'\n"
            f"Current Front VL53L0X ToF Distance: {tof_distance_mm} mm\n"
            f"Detected Marks Metadata: {json.dumps(som_metadata)}\n\n"
            "CRITICAL NAVIGATION RULES:\n"
            "1. Differentiate between INTERMEDIATE WAYPOINTS (e.g. [3] Free Corridor, detour lane) and the FINAL DESTINATION (e.g. [2] Blue Door).\n"
            "2. The command plan MUST NOT STOP inside the corridor. It must execute the complete multi-leg journey:\n"
            "   - Leg 1: Turn towards the detour / clear corridor [3].\n"
            "   - Leg 2: Drive forward to clear the obstacle [1].\n"
            "   - Leg 3: Turn to face the final destination [2] (Blue Door) directly.\n"
            "   - Leg 4: Drive forward along the clear path to reach the final destination [2].\n"
            "   - Leg 5: STOP at the final destination.\n\n"
            "Output pure JSON in this exact structure:\n"
            "{\n"
            '  "status": "success",\n'
            '  "identified_target": "[2] Blue Door (Final Goal)",\n'
            '  "identified_waypoint": "[3] Free Corridor (Intermediate Waypoint)",\n'
            '  "identified_obstacles": ["[1] Obstacle"],\n'
            '  "explanation": "Detailed step-by-step spatial route explaining how the robot passes the obstacle via the waypoint and reaches the final goal.",\n'
            '  "commands": [\n'
            '    {"action": "TURN_RIGHT", "degrees": 35, "speed": 160},\n'
            '    {"action": "FORWARD", "duration_s": 1.4, "speed": 160},\n'
            '    {"action": "TURN_LEFT", "degrees": 50, "speed": 160},\n'
            '    {"action": "FORWARD", "duration_s": 2.0, "speed": 160},\n'
            '    {"action": "STOP", "duration_s": 0, "speed": 0}\n'
            '  ]\n'
            "}"
        )

        content_parts = [prompt]

        # Extract PIL Image from base64 data URI if provided
        if image_data_uri and "base64," in image_data_uri:
            try:
                base64_data = image_data_uri.split("base64,")[1]
                image_bytes = base64.b64decode(base64_data)
                pil_img = Image.open(io.BytesIO(image_bytes))
                content_parts.append(pil_img)
            except Exception as e:
                logger.warning(f"Failed to decode image for Gemini: {e}")

        try:
            # Use non-blocking async execution
            if hasattr(self, "client") and self.client:
                from google.genai import types
                
                def _call_genai():
                    return self.client.models.generate_content(
                        model=self.model_name,
                        contents=content_parts,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.2
                        )
                    )
                response = await asyncio.to_thread(_call_genai)
            else:
                def _call_legacy():
                    return self.model.generate_content(content_parts)
                response = await asyncio.to_thread(_call_legacy)

            raw_text = response.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            elif raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()

            response_json = json.loads(raw_text)
            response_json["provider"] = f"Google Gemini ({self.model_name})"
            return response_json
        except Exception as e:
            logger.error(f"Error invoking Gemini API: {e}. Falling back to simulated reasoning.")
            return self._mock_reasoning(command_text, tof_distance_mm, som_metadata)

    def _mock_reasoning(
        self,
        command_text: str,
        tof_distance_mm: int,
        som_metadata: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        cmd_lower = command_text.lower()
        target = "[2] Target (Blue Door)" if "door" in cmd_lower else f"[2] Goal for '{command_text}'"
        is_close = tof_distance_mm < 350

        if is_close:
            explanation = (
                f"[SIMULATED GEMINI REASONING] Obstacle [1] detected ahead at {tof_distance_mm}mm. "
                f"Executing multi-leg route: (1) Turn right towards [3] Free Corridor, (2) Advance 1.4s past obstacle [1], "
                f"(3) Turn left 50° to face {target} directly, and (4) Drive forward 2.0s to arrive at {target}."
            )
            commands = [
                {"action": "TURN_RIGHT", "degrees": 35, "speed": 160},
                {"action": "FORWARD", "duration_s": 1.4, "speed": 160},
                {"action": "TURN_LEFT", "degrees": 50, "speed": 160},
                {"action": "FORWARD", "duration_s": 2.0, "speed": 160},
                {"action": "STOP", "duration_s": 0, "speed": 0}
            ]
        else:
            explanation = (
                f"[SIMULATED GEMINI REASONING] Path clear ({tof_distance_mm}mm). Direct approach toward {target}."
            )
            commands = [
                {"action": "FORWARD", "duration_s": 2.2, "speed": 180},
                {"action": "STOP", "duration_s": 0, "speed": 0}
            ]

        return {
            "status": "success",
            "is_mock": True,
            "provider": "Simulation (Waiting for Gemini API Key)",
            "identified_target": target,
            "identified_waypoint": "[3] Free Corridor",
            "identified_obstacles": ["[1] Obstacle"],
            "explanation": explanation,
            "commands": commands
        }

gemini_service = GeminiReasoningService()
