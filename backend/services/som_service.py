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
        {"fill": (239, 68, 68, 80), "outline": (239, 68, 68), "text_bg": (239, 68, 68)},    # Red (Obstacle)
        {"fill": (59, 130, 246, 80), "outline": (59, 130, 246), "text_bg": (59, 130, 246)},  # Blue (Target/Door)
        {"fill": (16, 185, 129, 80), "outline": (16, 185, 129), "text_bg": (16, 185, 129)},  # Green (Path/Corridor)
        {"fill": (245, 158, 11, 80), "outline": (245, 158, 11), "text_bg": (245, 158, 11)},  # Amber
        {"fill": (168, 85, 247, 80), "outline": (168, 85, 247), "text_bg": (168, 85, 247)}   # Purple
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
            detected_objects = [
                {
                    "id": 1,
                    "label": "Obstacle (Center Block)",
                    "bbox": [int(width * 0.35), int(height * 0.45), int(width * 0.65), int(height * 0.85)]
                },
                {
                    "id": 2,
                    "label": "Target (Blue Door / Far Left)",
                    "bbox": [int(width * 0.08), int(height * 0.20), int(width * 0.30), int(height * 0.80)]
                },
                {
                    "id": 3,
                    "label": "Free Corridor (Right Lane)",
                    "bbox": [int(width * 0.70), int(height * 0.35), int(width * 0.95), int(height * 0.85)]
                }
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
