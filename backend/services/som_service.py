import io
import base64
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont

class SetOfMarkService:
    """
    Set-of-Mark (SoM) Service:
    Overlays salient alphanumeric badges and bounding boxes directly onto image frames.
    Allows Vision-Language Models (GPT-4o) to reason over unambiguous spatial references.
    """

    COLOR_PALETTE = [
        {"fill": (239, 68, 68, 80), "outline": (239, 68, 68), "text_bg": (239, 68, 68)},    # [1] Red (Center Obstacle)
        {"fill": (59, 130, 246, 80), "outline": (59, 130, 246), "text_bg": (59, 130, 246)},  # [2] Blue (Blue Door Target)
        {"fill": (16, 185, 129, 80), "outline": (16, 185, 129), "text_bg": (16, 185, 129)},  # [3] Green (Free Corridor)
        {"fill": (234, 179, 8, 80), "outline": (234, 179, 8), "text_bg": (234, 179, 8)},    # [4] Amber/Yellow (Traffic Cone Hazard)
        {"fill": (6, 182, 212, 80), "outline": (6, 182, 212), "text_bg": (6, 182, 212)},    # [5] Cyan/Teal (Charging Station Dock)
        {"fill": (249, 115, 22, 80), "outline": (249, 115, 22), "text_bg": (249, 115, 22)},  # [6] Orange (Safety Barrel)
        {"fill": (168, 85, 247, 80), "outline": (168, 85, 247), "text_bg": (168, 85, 247)}   # [7] Purple (Lab Tool Bench)
    ]

    def annotate_frame(
        self,
        image_bytes: bytes,
        detected_objects: List[Dict[str, Any]] = None
    ) -> Tuple[bytes, List[Dict[str, Any]]]:
        """
        Annotates an image with Set-of-Mark numbered badges.
        If detected_objects is None or empty, generates intelligent default candidate marks for the scene.
        """
        image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        width, height = image.size

        # Create overlay layer for translucent bounding boxes
        overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
        draw_overlay = ImageDraw.Draw(overlay)
        draw = ImageDraw.Draw(image)

        # Default fallback objects if no detector model is running
        if not detected_objects:
            try:
                from backend.services.scene_generator import get_default_detected_objects
                detected_objects = get_default_detected_objects(width, height)
            except Exception:
                detected_objects = [
                    {"id": 1, "label": "Center Obstacle (Red Box)", "bbox": [int(width * 0.41), int(height * 0.51), int(width * 0.65), int(height * 0.83)]},
                    {"id": 2, "label": "Blue Door (Target)", "bbox": [int(width * 0.08), int(height * 0.23), int(width * 0.26), int(height * 0.71)]},
                    {"id": 3, "label": "Free Corridor (Right Lane)", "bbox": [int(width * 0.72), int(height * 0.45), int(width * 0.86), int(height * 0.90)]},
                    {"id": 4, "label": "Yellow Traffic Cone (Hazard)", "bbox": [int(width * 0.26), int(height * 0.63), int(width * 0.38), int(height * 0.88)]},
                    {"id": 5, "label": "Charging Station (Dock)", "bbox": [int(width * 0.86), int(height * 0.64), int(width * 0.99), int(height * 0.90)]},
                    {"id": 6, "label": "Orange Safety Barrel", "bbox": [int(width * 0.61), int(height * 0.52), int(width * 0.72), int(height * 0.75)]},
                    {"id": 7, "label": "Lab Tool Bench (Storage)", "bbox": [int(width * 0.28), int(height * 0.34), int(width * 0.41), int(height * 0.57)]}
                ]

        # Draw each mark
        for idx, obj in enumerate(detected_objects):
            mark_id = obj.get("id", idx + 1)
            label = obj.get("label", f"Object {mark_id}")
            x1, y1, x2, y2 = obj["bbox"]
            palette = self.COLOR_PALETTE[(mark_id - 1) % len(self.COLOR_PALETTE)]

            # Draw translucent bounding box
            draw_overlay.rectangle([x1, y1, x2, y2], fill=palette["fill"], outline=palette["outline"], width=3)

            # Draw solid high-contrast number badge [1], [2], [3]
            badge_text = f"[{mark_id}] {label}"
            badge_padding = 6
            text_size_approx = (len(badge_text) * 8, 18)
            badge_rect = [x1, max(0, y1 - 24), x1 + text_size_approx[0] + badge_padding * 2, max(24, y1)]

            # Draw badge background
            draw.rectangle(badge_rect, fill=palette["text_bg"])
            draw.text((x1 + badge_padding, max(2, y1 - 20)), badge_text, fill=(255, 255, 255))

        # Composite the overlay onto the original image
        annotated_image = Image.alpha_composite(image, overlay).convert("RGB")

        # Save to buffer
        out_buf = io.BytesIO()
        annotated_image.save(out_buf, format="JPEG", quality=88)
        annotated_bytes = out_buf.getvalue()

        return annotated_bytes, detected_objects

    @staticmethod
    def bytes_to_base64_data_uri(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
        b64_str = base64.b64encode(image_bytes).decode("utf-8")
        return f"data:{mime_type};base64,{b64_str}"

som_service = SetOfMarkService()
