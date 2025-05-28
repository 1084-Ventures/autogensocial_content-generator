import azure.functions as func
from azure.functions import Blueprint
import json
from PIL import Image, ImageDraw, ImageFont
import io

image_generation_blueprint = Blueprint()

@image_generation_blueprint.route(route="generate-image", methods=["POST"])
def generate_image(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
        text = data.get("text", "")
        visual_style = data.get("visualStyle", {})
        image_layout = data.get("imageLayout", {})
        width = image_layout.get("width", 800)
        height = image_layout.get("height", 600)
        font_family = visual_style.get("fontFamily", "Arial")
        font_size = int(visual_style.get("fontSize", "32").replace("px", ""))
        text_color = visual_style.get("textColor", "#000000")
        bg_color = visual_style.get("backgroundColor", "#FFFFFF")
        box_height = 80
        box_color = visual_style.get("boxColor", "#333333")

        # Create base image
        img = Image.new("RGB", (width, height + box_height), bg_color)
        draw = ImageDraw.Draw(img)

        # Draw the box below the image
        draw.rectangle([0, height, width, height + box_height], fill=box_color)

        # Load font
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

        # Draw the main text (centered)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = (width - text_width) // 2
        text_y = (height - text_height) // 2

        # Outline parameters
        outline_color = visual_style.get("outlineColor")
        outline_width = visual_style.get("outlineWidth", 0)
        # Draw main text with optional outline
        draw.text(
            (text_x, text_y),
            text,
            fill=text_color,
            font=font,
            stroke_width=outline_width if outline_color else 0,
            stroke_fill=outline_color if outline_color else None
        )

        # Draw box text if provided
        box_text = data.get("boxText", "")
        if box_text:
            box_bbox = draw.textbbox((0, 0), box_text, font=font)
            box_text_width = box_bbox[2] - box_bbox[0]
            box_text_height = box_bbox[3] - box_bbox[1]
            box_text_x = (width - box_text_width) // 2
            box_text_y = height + (box_height - box_text_height) // 2
            box_text_color = visual_style.get("boxTextColor", "#FFFFFF")
            draw.text(
                (box_text_x, box_text_y),
                box_text,
                fill=box_text_color,
                font=font,
                stroke_width=outline_width if outline_color else 0,
                stroke_fill=outline_color if outline_color else None
            )

        # Save to bytes
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        return func.HttpResponse(body=img_bytes.read(), mimetype="image/png", status_code=200)
    except Exception as e:
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")
