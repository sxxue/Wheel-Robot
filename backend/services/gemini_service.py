import os
import json
import base64
import logging
from typing import Dict, Any, List
from PIL import Image
import io

from backend.config import settings

logger = logging.getLogger(__name__)

class GeminiReasoningService:
    """
    Google Gemini Multimodal Vision & Reasoning Service
    Uses Gemini 1.5 Flash to inspect Set-of-Mark (SoM) annotated images
    and output deterministic JSON navigation sequences for the wheeled robot.
    """

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        self.client = None
        self.is_ready = False

        self._initialize_client()

    def _initialize_client(self):
        if not self.api_key or self.api_key.startswith("AIzaSyYourCopiedKey"):
            logger.info("Gemini API key not configured yet. Running in simulation fallback mode.")
            self.is_ready = False
            return

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.2,
                }
            )
            self.is_ready = True
            logger.info(f"✅ Google Gemini Model ({self.model_name}) initialized successfully!")
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
        # Re-check key in case it was updated dynamically in .env
        if not self.is_ready:
            self.api_key = os.getenv("GEMINI_API_KEY", "")
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
            "Analyze the spatial position of the target and obstacles, then generate a step-by-step navigation plan in pure JSON format:\n"
            "{\n"
            '  "status": "success",\n'
            '  "identified_target": "[2] Target Description",\n'
            '  "identified_obstacles": ["[1] Obstacle Description"],\n'
            '  "explanation": "Clear spatial reasoning explaining the route to avoid obstacles and reach the goal.",\n'
            '  "commands": [\n'
            '    {"action": "TURN_RIGHT", "degrees": 30, "speed": 160},\n'
            '    {"action": "FORWARD", "duration_s": 1.2, "speed": 170},\n'
            '    {"action": "TURN_LEFT", "degrees": 30, "speed": 160},\n'
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
            response = self.model.generate_content(content_parts)
            response_json = json.loads(response.text)
            response_json["provider"] = "Google Gemini 1.5 Flash"
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
                f"Steering right into [3] Free Corridor, advancing 1.2s, then realigning towards {target}."
            )
            commands = [
                {"action": "TURN_RIGHT", "degrees": 30, "speed": 160},
                {"action": "FORWARD", "duration_s": 1.2, "speed": 170},
                {"action": "TURN_LEFT", "degrees": 35, "speed": 160},
                {"action": "FORWARD", "duration_s": 1.0, "speed": 150},
                {"action": "STOP", "duration_s": 0, "speed": 0}
            ]
        else:
            explanation = (
                f"[SIMULATED GEMINI REASONING] Path clear ({tof_distance_mm}mm). Direct approach toward {target}."
            )
            commands = [
                {"action": "FORWARD", "duration_s": 1.5, "speed": 180},
                {"action": "STOP", "duration_s": 0, "speed": 0}
            ]

        return {
            "status": "success",
            "is_mock": True,
            "provider": "Simulation (Waiting for Gemini API Key)",
            "identified_target": target,
            "identified_obstacles": ["[1] Obstacle"],
            "explanation": explanation,
            "commands": commands
        }

gemini_service = GeminiReasoningService()
