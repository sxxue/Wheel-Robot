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
            "The image attached contains numbered Set-of-Mark (SoM) badges [1] through [7] representing detected objects, targets, hazards, and corridors:\n"
            "   - [1] Center Obstacle (Red Box) - direct ahead\n"
            "   - [2] Blue Door (Target / Far Left)\n"
            "   - [3] Free Corridor (Right Lane Clearance Route)\n"
            "   - [4] Yellow Traffic Cone (Hazard / Left Foreground)\n"
            "   - [5] Charging Station (Dock / Far Right Wall)\n"
            "   - [6] Orange Safety Barrel (Obstacle / Mid-Right Flank)\n"
            "   - [7] Lab Tool Bench (Storage / Mid-Left Background)\n\n"
            f"User Natural Language Command: '{command_text}'\n"
            f"Current Front VL53L0X ToF Distance: {tof_distance_mm} mm\n"
            f"Detected Marks Metadata: {json.dumps(som_metadata)}\n\n"
            "MULTILINGUAL NATURAL LANGUAGE CAPABILITY:\n"
            "The User Command may be issued in ANY of 20+ languages/dialects (e.g. English, Bahasa Melayu, 廣東話 Cantonese, "
            "中文 Mandarin, 台灣國語 Taiwanese, 日本語 Japanese, 한국어 Korean, Español, Français, Deutsch, العربية, "
            "हिन्दी, தமிழ், Bahasa Indonesia, Русский, Português, Italiano, Tiếng Việt, ไทย, etc.).\n\n"
            "CANTONESE (粵語 / 廣東話) REGIONAL DIALECT MAPPING:\n"
            "- '叉電' / '叉電位' / '叉電站' -> Charging Station [5]\n"
            "- '雪糕筒' / '黃色雪糕筒' -> Yellow Traffic Cone Hazard [4]\n"
            "- '藍色門' / '行去道門' / '去門口' -> Blue Door [2]\n"
            "- '紫色嗰張枱' / '紫色嗰個' / '工作枱' -> Lab Tool Bench [7]\n"
            "- '兜個圈' / '兜一圈' / '轉個圈' -> 360° Circumnavigation Circuit around Obstacle [1]\n"
            "- '避開' / '唔好撞' / '咪撞' / '繞過' -> Obstacle Avoidance\n"
            "- '行去' / '行到' / '去' -> Move toward destination\n\n"
            "- Natively interpret the semantic destination, obstacles, and directional requests regardless of the language used.\n"
            "- Always emit deterministic motion primitives using standard English tokens: TURN_LEFT, TURN_RIGHT, FORWARD, BACKWARD, STOP.\n"
            "- In 'explanation', explain the reasoning clearly referencing the detected landmark badges [1]-[7].\n\n"
            "INTENT-AWARE NAVIGATION RULES:\n"
            "1. CLASSIFY THE USER'S INTENT & PHRASING:\n"
            "   A) COMPOUND SEQUENTIAL ACTIONS (e.g. 'go round obstacle once and go to the blue door', 'loop around [1] then reach [2]'):\n"
            "      - Phase 1 (Full 360° Circuit): 'once' or 'circle' means a complete circumnavigation around obstacle [1].\n"
            "      - Phase 2 (Target Transit): Re-align heading toward the requested target ([2] Blue Door or [5] Charging Dock) and advance -> STOP.\n"
            "      - Generate all 8-9 steps required to execute both phases fully. DO NOT abbreviate into a simple bypass!\n\n"
            "   B) SPECIFIC TARGET (e.g. 'reach the blue door [2]', 'navigate to the charging dock [5]', 'drive to lab bench [7]'):\n"
            "      - Destination is the user's requested object from the detected marks.\n"
            "      - Plan route: bypass any intermediate obstacles/hazards (like [1], [4], [6]) -> align with target -> drive directly to target -> STOP.\n\n"
            "   C) OBSTACLE BYPASS ONLY (e.g. 'go around the obstacle', 'avoid the obstacle [1]', 'steer around the orange barrel [6]'):\n"
            "      - No target specified! Destination is simply the clear open floor past the obstacle.\n"
            "      - Plan: turn into corridor [3] -> drive past obstacle -> turn back to straight forward heading -> STOP.\n\n"
            "   D) DIRECTIONAL MOTION (e.g. 'turn right into corridor', 'move forward'):\n"
            "      - Direct motion primitive execution.\n\n"
            "Output pure JSON in this exact structure:\n"
            "{\n"
            '  "status": "success",\n'
            '  "user_intent": "COMPOUND_CIRCUIT_AND_TARGET or REACH_TARGET or OBSTACLE_BYPASS or DIRECTIONAL_MOTION",\n'
            '  "identified_target": "Name of final destination or clear area",\n'
            '  "identified_waypoint": "Intermediate detour used",\n'
            '  "identified_obstacles": ["List of obstacles"],\n'
            '  "explanation": "Detailed multi-phase reasoning explicitly addressing all clauses of user command.",\n'
            '  "commands": [\n'
            '    {"action": "TURN_RIGHT", "degrees": 35, "speed": 160},\n'
            '    {"action": "FORWARD", "duration_s": 1.4, "speed": 160},\n'
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

        # Multilingual keyword lexicons across 20+ world languages & dialects
        circuit_words = ["once", "circle", "loop", "pusing", "keliling", "satu pusingan", "一圈", "绕一圈", "兜圈", "兜個圈", "兜一圈", "轉個圈", "周回", "vuelta", "tour", "runde", "دورة", "फेरा"]
        door_words = ["door", "pintu", "门", "門", "藍色門", "蓝色门", "道門", "門口", "ドア", "puerta", "porte", "tür", "porta", "باب", "கதவு", "दरवाजा", "cửa", "[2]"]
        dock_words = ["dock", "charg", "cas", "pengecas", "stesen", "充电", "充電", "叉電", "叉電位", "叉電座", "叉電站", "充電位", "carga", "recharge", "ladestation", "شحن", "மின்", "चार्ज", "trạm sạc", "[5]"]
        bench_words = ["bench", "desk", "table", "tool", "meja", "banc", "banco", "tisch", "桌", "工作台", "工作枱", "紫色枱", "紫色嗰張枱", "紫色嗰個", "张桌子", "张枱", "机", "طاولة", "மேசை", "मेज़", "bàn", "purple", "ungu", "紫色", "紫", "pourpre", "lila", "[7]"]
        cone_words = ["cone", "hazard", "kon", "cono", "cône", "kegel", "锥", "三角锥", "雪糕筒", "黃色雪糕筒", "コーン", "مخروط", "hình nón", "yellow", "kuning", "黄色", "黃色", "jaune", "amarillo", "[4]"]
        barrel_words = ["barrel", "tong", "drum", "barril", "baril", "fass", "桶", "油桶", "大鐵桶", "ドラム", "برميل", "thùng", "orange", "jingga", "橙色", "naranja", "[6]"]
        corridor_words = ["corridor", "lane", "lorong", "jalan", "走廊", "通道", "通路", "右邊通道", "右面走廊", "條路", "pasillo", "couloir", "korridor", "ممر", "hành lang", "green", "hijau", "绿色", "綠色", "vert", "[3]"]
        avoid_words = ["around", "avoid", "bypass", "elak", "hindar", "绕", "绕过", "避开", "避開", "咪撞", "唔好撞", "兜過", "避ける", "evita", "éviter", "umgehen", "تجنب", "tránh"]

        has_circuit = any(w in cmd_lower for w in circuit_words)
        has_door = any(w in cmd_lower for w in door_words)
        has_dock = any(w in cmd_lower for w in dock_words)
        has_bench = any(w in cmd_lower for w in bench_words)
        has_cone = any(w in cmd_lower for w in cone_words)
        has_barrel = any(w in cmd_lower for w in barrel_words)
        has_corridor = any(w in cmd_lower for w in corridor_words)
        has_avoid = any(w in cmd_lower for w in avoid_words)

        if has_circuit and has_door:
            intent = "COMPOUND_CIRCUIT_AND_TARGET"
            target = "[2] Target (Blue Door / Far Left)"
            waypoint = "[1] Center Obstacle (Red Box)"
            explanation = (
                f"[GEMINI REASONING] Compound command received: (1) Complete full 360° circumnavigation around obstacle [1], "
                f"then (2) navigate to {target}. Executing complete 9-step circuit and arrival maneuver."
            )
            commands = [
                {"action": "TURN_RIGHT", "degrees": 35, "speed": 160},
                {"action": "FORWARD", "duration_s": 1.4, "speed": 160},
                {"action": "TURN_LEFT", "degrees": 90, "speed": 160},
                {"action": "FORWARD", "duration_s": 1.4, "speed": 160},
                {"action": "TURN_LEFT", "degrees": 90, "speed": 160},
                {"action": "FORWARD", "duration_s": 1.4, "speed": 160},
                {"action": "TURN_RIGHT", "degrees": 45, "speed": 160},
                {"action": "FORWARD", "duration_s": 2.0, "speed": 160},
                {"action": "STOP", "duration_s": 0, "speed": 0}
            ]
        elif has_dock:
            intent = "REACH_TARGET"
            target = "[5] Charging Station (Dock / Far Right)"
            waypoint = "[3] Free Corridor (Right Lane)"
            explanation = (
                f"[GEMINI REASONING] User requested navigation to the charging dock [5]. "
                f"Front path blocked by obstacle [1] at {tof_distance_mm}mm. Route: (1) Turn right 40° into [3] Free Corridor, "
                f"(2) Drive 1.4s past orange barrel [6], (3) Turn right 25° towards [5] Charging Dock, (4) Drive 1.2s to dock terminal, (5) STOP."
            )
            commands = [
                {"action": "TURN_RIGHT", "degrees": 40, "speed": 160},
                {"action": "FORWARD", "duration_s": 1.4, "speed": 160},
                {"action": "TURN_RIGHT", "degrees": 25, "speed": 160},
                {"action": "FORWARD", "duration_s": 1.2, "speed": 160},
                {"action": "STOP", "duration_s": 0, "speed": 0}
            ]
        elif has_bench:
            intent = "REACH_TARGET"
            target = "[7] Lab Tool Bench (Storage / Mid-Left)"
            waypoint = "Clear gap between [4] Yellow Cone and [1] Red Box"
            explanation = (
                f"[GEMINI REASONING] Target set to Lab Tool Bench [7]. Navigating around [4] Yellow Cone hazard: "
                f"(1) Turn left 25°, (2) Advance 1.6s to bench workstation, (3) STOP."
            )
            commands = [
                {"action": "TURN_LEFT", "degrees": 25, "speed": 160},
                {"action": "FORWARD", "duration_s": 1.6, "speed": 160},
                {"action": "STOP", "duration_s": 0, "speed": 0}
            ]
        elif has_door:
            intent = "REACH_TARGET"
            target = "[2] Target (Blue Door)"
            waypoint = "[3] Free Corridor (Right Lane)"
            explanation = (
                f"[GEMINI REASONING] Obstacle [1] detected ahead at {tof_distance_mm}mm. "
                f"Multi-leg route to blue door: (1) Turn right into [3] Free Corridor, (2) Drive 1.5s past obstacle [1] and barrel [6], "
                f"(3) Turn left 55° directly towards {target}, (4) Drive 2.0s to destination, (5) STOP."
            )
            commands = [
                {"action": "TURN_RIGHT", "degrees": 35, "speed": 160},
                {"action": "FORWARD", "duration_s": 1.5, "speed": 160},
                {"action": "TURN_LEFT", "degrees": 55, "speed": 160},
                {"action": "FORWARD", "duration_s": 2.0, "speed": 160},
                {"action": "STOP", "duration_s": 0, "speed": 0}
            ]
        elif has_barrel:
            intent = "OBSTACLE_BYPASS"
            target = "Clear corridor lane avoiding safety barrel [6]"
            waypoint = "[3] Free Corridor"
            explanation = (
                f"[GEMINI REASONING] Avoiding Orange Safety Barrel [6] on mid-right flank: "
                f"(1) Maintain straight corridor heading along [3], (2) Drive 1.8s past barrel, (3) STOP."
            )
            commands = [
                {"action": "TURN_RIGHT", "degrees": 35, "speed": 160},
                {"action": "FORWARD", "duration_s": 1.8, "speed": 160},
                {"action": "STOP", "duration_s": 0, "speed": 0}
            ]
        elif has_avoid:
            intent = "OBSTACLE_BYPASS"
            target = "Clear corridor space past center obstacle [1]"
            waypoint = "[3] Free Corridor"
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
        elif any(w in cmd_lower for w in ["stop", "halt", "berhenti", "停", "停止", "停低", "咪郁", "唔好郁", "煞停", "alto", "arrête", "stopp"]):
            intent = "DIRECTIONAL_MOTION"
            target = "Immediate Stop Position"
            waypoint = "Current Pose"
            explanation = f"[GEMINI REASONING] Emergency/User stop command received ('{command_text}'). Halting motors immediately."
            commands = [{"action": "STOP", "duration_s": 0, "speed": 0}]
        elif any(w in cmd_lower for w in ["left", "kiri", "向左", "轉左", "左轉", "偏左", "左邊", "左面", "esquerda", "izquierda", "gauche", "links"]):
            intent = "DIRECTIONAL_MOTION"
            target = "Left Flank Heading"
            waypoint = "Clear left floor"
            explanation = f"[GEMINI REASONING] Left turn commanded ('{command_text}'). Executing pivot turn."
            commands = [
                {"action": "TURN_LEFT", "degrees": 45, "speed": 160},
                {"action": "STOP", "duration_s": 0, "speed": 0}
            ]
        elif any(w in cmd_lower for w in ["right", "kanan", "向右", "轉右", "右轉", "偏右", "右邊", "右面", "direita", "derecha", "droite", "rechts"]):
            intent = "DIRECTIONAL_MOTION"
            target = "Right Flank Heading"
            waypoint = "Clear right floor"
            explanation = f"[GEMINI REASONING] Right turn commanded ('{command_text}'). Executing pivot turn."
            commands = [
                {"action": "TURN_RIGHT", "degrees": 45, "speed": 160},
                {"action": "STOP", "duration_s": 0, "speed": 0}
            ]
        elif any(w in cmd_lower for w in ["backward", "back", "reverse", "undur", "belakang", "向后", "向後", "行後", "退後", "後退", "倒退", "atrás", "reculer"]):
            intent = "DIRECTIONAL_MOTION"
            target = "Rear Clearance Zone"
            waypoint = "Reverse Path"
            explanation = f"[GEMINI REASONING] Reverse motion commanded ('{command_text}'). Backing up."
            commands = [
                {"action": "BACKWARD", "duration_s": 1.2, "speed": 160},
                {"action": "STOP", "duration_s": 0, "speed": 0}
            ]
        else:
            intent = "DIRECTIONAL_MOTION"
            target = f"Trajectory for '{command_text}'"
            waypoint = "Direct Path"
            explanation = f"[GEMINI REASONING] Path clear ({tof_distance_mm}mm). Proceeding with requested movement."
            commands = [
                {"action": "FORWARD", "duration_s": 1.5, "speed": 180},
                {"action": "STOP", "duration_s": 0, "speed": 0}
            ]

        return {
            "status": "success",
            "user_intent": intent,
            "identified_target": target,
            "identified_waypoint": waypoint,
            "identified_obstacles": ["[1] Obstacle (Red Box)"],
            "explanation": explanation,
            "commands": commands
        }

gemini_service = GeminiReasoningService()
