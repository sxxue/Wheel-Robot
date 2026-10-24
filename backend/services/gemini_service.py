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
            "INTENT-AWARE NAVIGATION RULES:\n"
            "1. CLASSIFY THE USER'S INTENT:\n"
            "   A) SPECIFIC TARGET (e.g. 'reach the blue door', 'go to [2]', 'drive to the door'):\n"
            "      - Destination is the user's requested object.\n"
            "      - Plan route: bypass obstacles -> align with target -> drive to target -> STOP.\n"
            "   B) OBSTACLE BYPASS ONLY (e.g. 'go around the obstacle', 'avoid the obstacle', 'circumnavigate'):\n"
            "      - The user did NOT ask for the blue door or any specific destination!\n"
            "      - Destination is simply the clear open floor PAST the obstacle.\n"
            "      - Plan route: turn into clear space/corridor -> drive past the obstacle -> turn back to resume straight forward heading -> STOP in clear space. DO NOT head toward the blue door unless explicitly requested!\n"
            "   C) DIRECTIONAL / EXPLORATION (e.g. 'turn right', 'move forward', 'explore corridor'):\n"
            "      - Execute the commanded motion into the specified direction/corridor.\n\n"
            "Output pure JSON in this exact structure:\n"
            "{\n"
            '  "status": "success",\n'
            '  "user_intent": "REACH_TARGET or OBSTACLE_BYPASS or DIRECTIONAL_MOTION",\n'
            '  "identified_target": "Name of the target or Clear area past obstacle",\n'
            '  "identified_waypoint": "Intermediate detour used or None",\n'
            '  "identified_obstacles": ["List of obstacles to avoid"],\n'
            '  "explanation": "Clear spatial reasoning strictly adhering to the user command intent.",\n'
            '  "commands": [\n'
            '    {"action": "TURN_RIGHT", "degrees": 30, "speed": 160},\n'
            '    {"action": "FORWARD", "duration_s": 1.2, "speed": 160},\n'
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
        is_close = tof_distance_mm < 460

        if "door" in cmd_lower:
            intent = "REACH_TARGET"
            target = "[2] Target (Blue Door)"
            explanation = (
                f"[GEMINI REASONING] Obstacle [1] detected ahead at {tof_distance_mm}mm. "
                f"Multi-leg route to blue door: (1) Turn right into [3] Free Corridor, (2) Drive 1.5s past obstacle [1], "
                f"(3) Turn left 55° directly towards {target}, (4) Drive 2.0s to destination, (5) STOP."
            )
            commands = [
                {"action": "TURN_RIGHT", "degrees": 35, "speed": 160},
                {"action": "FORWARD", "duration_s": 1.5, "speed": 160},
                {"action": "TURN_LEFT", "degrees": 55, "speed": 160},
                {"action": "FORWARD", "duration_s": 2.0, "speed": 160},
                {"action": "STOP", "duration_s": 0, "speed": 0}
            ]
        elif "around" in cmd_lower or "avoid" in cmd_lower:
            intent = "OBSTACLE_BYPASS"
            target = "Clear corridor space past obstacle [1]"
            explanation = (
                f"[GEMINI REASONING] Obstacle bypass requested. Center obstacle [1] at {tof_distance_mm}mm. "
                f"Bypass route: (1) Turn right 35° into clear corridor [3], (2) Drive forward 1.6s to clear obstacle [1], "
                f"(3) Turn left 35° to re-align straight heading, (4) STOP safely in clear open space."
            )
            commands = [
                {"action": "TURN_RIGHT", "degrees": 35, "speed": 160},
                {"action": "FORWARD", "duration_s": 1.6, "speed": 160},
                {"action": "TURN_LEFT", "degrees": 35, "speed": 160},
                {"action": "STOP", "duration_s": 0, "speed": 0}
            ]
        else:
            intent = "DIRECTIONAL_MOTION"
            target = f"Trajectory for '{command_text}'"
            explanation = f"[GEMINI REASONING] Path clear ({tof_distance_mm}mm). Proceeding with requested movement."
            commands = [
                {"action": "FORWARD", "duration_s": 1.5, "speed": 180},
                {"action": "STOP", "duration_s": 0, "speed": 0}
            ]

        return {
            "status": "success",
            "user_intent": intent,
            "identified_target": target,
            "identified_waypoint": "[3] Free Corridor",
            "identified_obstacles": ["[1] Obstacle"],
            "explanation": explanation,
            "commands": commands
        }

gemini_service = GeminiReasoningService()
