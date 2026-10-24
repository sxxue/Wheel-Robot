import json
import logging
from typing import Dict, Any, List
from backend.config import settings

logger = logging.getLogger(__name__)

class AzureOpenAIService:
    def __init__(self):
        self.use_mock = settings.USE_MOCK_AZURE or not bool(settings.AZURE_OPENAI_API_KEY)
        self.client = None

        if not self.use_mock:
            try:
                from openai import AzureOpenAI
                self.client = AzureOpenAI(
                    azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
                    api_key=settings.AZURE_OPENAI_API_KEY,
                    api_version=settings.AZURE_OPENAI_API_VERSION
                )
                logger.info("Azure OpenAI Client initialized successfully.")
            except Exception as e:
                logger.warning(f"Failed to initialize Azure OpenAI client: {e}. Falling back to mock reasoning.")
                self.use_mock = True

    async def plan_navigation(
        self,
        command_text: str,
        tof_distance_mm: int,
        som_metadata: List[Dict[str, Any]],
        image_data_uri: str = None
    ) -> Dict[str, Any]:
        """
        Takes the user natural language command, current ToF distance, and SoM marked objects,
        and prompts Azure OpenAI (GPT-4o) to output a deterministic motion plan.
        """
        if self.use_mock:
            return self._mock_reasoning(command_text, tof_distance_mm, som_metadata)

        system_prompt = (
            "You are the navigation planner for an autonomous 2WD wheeled robot equipped with a camera "
            "and a front Time-of-Flight (VL53L0X) distance sensor. The image provided contains numbered "
            "Set-of-Mark (SoM) visual annotations [1], [2], [3] representing detected objects and corridors.\n"
            "Given the user's natural language command and the current front ToF sensor reading, output a strict "
            "JSON object with the following schema:\n"
            "{\n"
            '  "identified_target": "[2] Blue Door",\n'
            '  "identified_obstacles": ["[1] Obstacle"],\n'
            '  "explanation": "Brief reasoning description",\n'
            '  "commands": [\n'
            '    {"action": "TURN_RIGHT", "degrees": 30, "speed": 160},\n'
            '    {"action": "FORWARD", "duration_s": 1.2, "speed": 170},\n'
            '    {"action": "TURN_LEFT", "degrees": 30, "speed": 160},\n'
            '    {"action": "STOP", "duration_s": 0, "speed": 0}\n'
            "  ]\n"
            "}"
        )

        user_content = [
            {
                "type": "text",
                "text": f"User Natural Language Command: '{command_text}'\n"
                        f"Current Front VL53L0X ToF Distance: {tof_distance_mm} mm\n"
                        f"Detected Marks Metadata: {json.dumps(som_metadata)}"
            }
        ]

        if image_data_uri:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": image_data_uri, "detail": "low"}
            })

        try:
            response = self.client.chat.completions.create(
                model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=600
            )
            raw_json = response.choices[0].message.content
            return json.loads(raw_json)
        except Exception as e:
            logger.error(f"Error calling Azure OpenAI: {e}. Falling back to mock reasoning.")
            return self._mock_reasoning(command_text, tof_distance_mm, som_metadata)

    def _mock_reasoning(
        self,
        command_text: str,
        tof_distance_mm: int,
        som_metadata: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """High-fidelity mock planner for testing when Azure OpenAI is offline or not configured."""
        cmd_lower = command_text.lower()
        
        target = "[2] Blue Door"
        obstacle = "[1] Obstacle"
        
        # Check if obstacle is close according to VL53L0X reading
        is_obstacle_close = tof_distance_mm < 300

        if "blue door" in cmd_lower or "door" in cmd_lower:
            target_desc = "[2] Target (Blue Door)"
        else:
            target_desc = f"[2] Recognized Target for '{command_text}'"

        if is_obstacle_close:
            explanation = (
                f"[MOCK REASONING] Obstacle {obstacle} detected directly ahead at {tof_distance_mm}mm. "
                f"Executing avoidance maneuver by diverting right into [3] Free Corridor, "
                f"advancing 1.2s, then realigning heading toward target {target_desc}."
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
                f"[MOCK REASONING] Front distance is clear ({tof_distance_mm}mm). "
                f"Proceeding towards target {target_desc}."
            )
            commands = [
                {"action": "FORWARD", "duration_s": 1.5, "speed": 180},
                {"action": "STOP", "duration_s": 0, "speed": 0}
            ]

        return {
            "status": "success",
            "is_mock": True,
            "identified_target": target_desc,
            "identified_obstacles": [obstacle],
            "explanation": explanation,
            "commands": commands
        }

azure_openai_service = AzureOpenAIService()
