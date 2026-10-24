import io
import time
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont

def get_default_detected_objects(width: int = 640, height: int = 480) -> List[Dict[str, Any]]:
    """Returns normalized bounding boxes and labels for the benchmark multi-object scene."""
    return [
        {
            "id": 1,
            "label": "Center Obstacle (Red Box)",
            "bbox": [int(width * 0.41), int(height * 0.51), int(width * 0.65), int(height * 0.83)]
        },
        {
            "id": 2,
            "label": "Blue Door (Target)",
            "bbox": [int(width * 0.08), int(height * 0.23), int(width * 0.26), int(height * 0.71)]
        },
        {
            "id": 3,
            "label": "Free Corridor (Right Lane)",
            "bbox": [int(width * 0.72), int(height * 0.45), int(width * 0.86), int(height * 0.90)]
        },
        {
            "id": 4,
            "label": "Yellow Traffic Cone (Hazard)",
            "bbox": [int(width * 0.26), int(height * 0.63), int(width * 0.38), int(height * 0.88)]
        },
        {
            "id": 5,
            "label": "Charging Station (Dock)",
            "bbox": [int(width * 0.86), int(height * 0.64), int(width * 0.99), int(height * 0.90)]
        },
        {
            "id": 6,
            "label": "Orange Safety Barrel",
            "bbox": [int(width * 0.61), int(height * 0.52), int(width * 0.72), int(height * 0.75)]
        },
        {
            "id": 7,
            "label": "Lab Tool Bench (Storage)",
            "bbox": [int(width * 0.28), int(height * 0.34), int(width * 0.41), int(height * 0.57)]
        }
    ]

def render_multi_object_scene(width: int = 640, height: int = 480, timestamp_text: str = None) -> bytes:
    """
    Renders a high-fidelity synthetic indoor environment with 7 salient objects
    for benchmark Set-of-Mark (SoM) multimodal spatial reasoning.
    """
    img = Image.new("RGB", (width, height), color=(18, 24, 38))
    draw = ImageDraw.Draw(img)

    # 1. Background Wall & Horizon
    wall_bottom = int(height * 0.44)
    draw.rectangle([0, 0, width, wall_bottom], fill=(24, 32, 50))
    # Wall baseboard trim
    draw.rectangle([0, wall_bottom - 5, width, wall_bottom + 2], fill=(51, 65, 85))

    # 2. Perspective Floor
    draw.polygon([(0, height), (width, height), (int(width * 0.84), wall_bottom), (int(width * 0.16), wall_bottom)], fill=(38, 48, 68))

    # Floor Grid Depth Lines
    for x_pos in [int(width * 0.19), int(width * 0.34), int(width * 0.50), int(width * 0.66), int(width * 0.81)]:
        top_x = int(width * 0.50 + (x_pos - width * 0.50) * 0.45)
        draw.line([(top_x, wall_bottom), (x_pos, height)], fill=(52, 65, 90), width=1)
    for y_pos in [int(height * 0.50), int(height * 0.58), int(height * 0.69), int(height * 0.82)]:
        draw.line([(0, y_pos), (width, y_pos)], fill=(48, 60, 84), width=1)

    # 3. [2] Blue Door (Left Wall)
    d_x1, d_y1, d_x2, d_y2 = int(width * 0.08), int(height * 0.23), int(width * 0.26), int(height * 0.71)
    draw.rectangle([d_x1, d_y1, d_x2, d_y2], fill=(20, 35, 70), outline=(96, 165, 250), width=2)
    draw.rectangle([d_x1 + 8, d_y1 + 8, d_x2 - 8, d_y2 - 8], fill=(37, 99, 235))
    draw.rectangle([d_x1 + 16, d_y1 + 20, d_x2 - 16, int(d_y1 + (d_y2 - d_y1) * 0.42)], fill=(29, 78, 216), outline=(96, 165, 250), width=1)
    draw.rectangle([d_x1 + 16, int(d_y1 + (d_y2 - d_y1) * 0.50), d_x2 - 16, d_y2 - 20], fill=(29, 78, 216), outline=(96, 165, 250), width=1)
    draw.ellipse([d_x2 - 25, int((d_y1 + d_y2) * 0.5), d_x2 - 15, int((d_y1 + d_y2) * 0.5) + 10], fill=(253, 224, 71)) # Brass Knob

    # 4. [7] Lab Tool Bench (Mid-Left Background)
    b_x1, b_y1, b_x2, b_y2 = int(width * 0.28), int(height * 0.38), int(width * 0.41), int(height * 0.57)
    draw.rectangle([b_x1, b_y1 + 10, b_x2, b_y1 + 20], fill=(148, 163, 184)) # Table top
    draw.line([(b_x1 + 5, b_y1 + 20), (b_x1 + 5, b_y2)], fill=(71, 85, 105), width=3) # Left leg
    draw.line([(b_x2 - 5, b_y1 + 20), (b_x2 - 5, b_y2)], fill=(71, 85, 105), width=3) # Right leg
    draw.rectangle([b_x1 + 10, b_y1 - 10, b_x2 - 15, b_y1 + 10], fill=(30, 41, 59), outline=(100, 116, 139), width=1) # Instrument
    draw.rectangle([b_x1 + 30, b_y1 - 5, b_x2 - 20, b_y1 + 5], fill=(34, 197, 94)) # Digital green display

    # 5. [4] Yellow Traffic Cone (Foreground Left)
    c_x1, c_y1, c_x2, c_y2 = int(width * 0.26), int(height * 0.63), int(width * 0.38), int(height * 0.88)
    cx_mid = (c_x1 + c_x2) // 2
    draw.polygon([(cx_mid, c_y1), (c_x1 + 5, c_y2 - 10), (c_x2 - 5, c_y2 - 10)], fill=(234, 179, 8))
    # Cone reflective collar
    col_top = c_y1 + int((c_y2 - c_y1) * 0.35)
    col_bot = c_y1 + int((c_y2 - c_y1) * 0.65)
    draw.polygon([(cx_mid - 7, col_top), (c_x1 + 20, col_bot), (c_x2 - 20, col_bot), (cx_mid + 7, col_top)], fill=(241, 245, 249))
    draw.ellipse([c_x1, c_y2 - 15, c_x2, c_y2], fill=(202, 138, 4)) # Base

    # 6. [1] Center Red Cardboard Obstacle Box (Isometric 3D)
    o_x1, o_y1, o_x2, o_y2 = int(width * 0.41), int(height * 0.57), int(width * 0.59), int(height * 0.83)
    depth_x, depth_y = int(width * 0.05), int(height * 0.06)
    # Front face
    draw.rectangle([o_x1, o_y1, o_x2, o_y2], fill=(220, 38, 38), outline=(254, 202, 202), width=1)
    # Top face
    draw.polygon([(o_x1, o_y1), (o_x1 + depth_x, o_y1 - depth_y), (o_x2 + depth_x, o_y1 - depth_y), (o_x2, o_y1)], fill=(239, 68, 68))
    # Side face
    draw.polygon([(o_x2, o_y1), (o_x2 + depth_x, o_y1 - depth_y), (o_x2 + depth_x, o_y2 - depth_y), (o_x2, o_y2)], fill=(185, 28, 28))
    # Warning hazard sign on box
    draw.rectangle([o_x1 + 30, o_y1 + 35, o_x2 - 30, o_y2 - 35], fill=(245, 158, 11))
    draw.text((o_x1 + 38, o_y1 + 45), "DANGER", fill=(0, 0, 0))

    # 7. [6] Orange Safety Barrel (Obstacle Mid-Right)
    s_x1, s_y1, s_x2, s_y2 = int(width * 0.61), int(height * 0.52), int(width * 0.72), int(height * 0.75)
    draw.rectangle([s_x1, s_y1 + 8, s_x2, s_y2 - 5], fill=(249, 115, 22))
    draw.ellipse([s_x1, s_y1, s_x2, s_y1 + 16], fill=(251, 146, 60))
    draw.rectangle([s_x1, s_y1 + 30, s_x2, s_y1 + 46], fill=(248, 250, 252)) # Reflective band 1
    draw.rectangle([s_x1, s_y1 + 65, s_x2, s_y1 + 81], fill=(248, 250, 252)) # Reflective band 2
    draw.ellipse([s_x1 - 2, s_y2 - 12, s_x2 + 2, s_y2], fill=(30, 41, 59)) # Base rim

    # 8. [3] Free Corridor (Right Lane Clearance Zone)
    f_x1, f_y1, f_x2, f_y2 = int(width * 0.72), int(height * 0.45), int(width * 0.86), int(height * 0.90)
    draw.rectangle([f_x1, f_y1, f_x2, f_y2], outline=(52, 211, 153), width=2)
    # Forward green guidance arrows
    for step_ratio in [0.25, 0.50, 0.75]:
        cy = int(f_y1 + (f_y2 - f_y1) * step_ratio)
        cx = (f_x1 + f_x2) // 2
        draw.polygon([(cx, cy - 14), (cx - 20, cy + 6), (cx - 10, cy + 6), (cx, cy - 4), (cx + 10, cy + 6), (cx + 20, cy + 6)], fill=(16, 185, 129))

    # 9. [5] Charging Station Dock (Far Right)
    k_x1, k_y1, k_x2, k_y2 = int(width * 0.86), int(height * 0.64), int(width * 0.99), int(height * 0.90)
    # Floor contact base pad
    draw.polygon([(k_x1, int(k_y2 * 0.90)), (k_x2, int(k_y2 * 0.88)), (k_x2 + 5, k_y2), (k_x1 + 5, k_y2)], fill=(15, 118, 110))
    # Terminal upright tower
    draw.rectangle([k_x1 + 15, k_y1, k_x2 - 10, int(k_y2 * 0.90)], fill=(13, 148, 136), outline=(45, 212, 191), width=2)
    # Yellow charging lightning symbol
    tw_cx = (k_x1 + 15 + k_x2 - 10) // 2
    draw.polygon([(tw_cx, k_y1 + 15), (tw_cx - 10, k_y1 + 38), (tw_cx + 2, k_y1 + 38), (tw_cx - 5, k_y1 + 58), (tw_cx + 12, k_y1 + 30), (tw_cx, k_y1 + 30)], fill=(250, 204, 21))
    draw.ellipse([k_x1 + 22, k_y1 + 10, k_x1 + 28, k_y1 + 16], fill=(52, 211, 153)) # Online LED

    # Header Overlay / Timestamp
    if timestamp_text:
        draw.text((20, 20), timestamp_text, fill=(56, 189, 248))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()
