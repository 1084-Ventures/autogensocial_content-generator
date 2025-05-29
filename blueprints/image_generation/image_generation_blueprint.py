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
        image = data.get("image", {})
        # Extract from new visualStyle structure
        font = visual_style.get("font", {})
        color = visual_style.get("color", {})
        outline = visual_style.get("outline", {})
        alignment = visual_style.get("alignment", {})
        # Font
        font_family = font.get("family", "Arial")
        font_size = int(font.get("size", "32").replace("px", ""))
        font_weight = font.get("weight", "normal")
        font_style = font.get("style", "normal")
        # Colors
        text_color = color.get("text", "#000000")
        bg_color = color.get("background", "#FFFFFF")
        box_color = color.get("box", "#333333")
        box_text_color = color.get("boxText", "#FFFFFF")
        # Outline
        outline_color = outline.get("color")
        outline_width = outline.get("width", 0)
        # Alignment
        text_align = alignment.get("textAlign", "center")
        # Image layout
        width = image.get("container", {}).get("width", 800)
        height = image.get("container", {}).get("height", 600)
        box_height = 80

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

        # Draw the main text (centered or aligned)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        if text_align == "left":
            text_x = 10
        elif text_align == "right":
            text_x = width - text_width - 10
        else:
            text_x = (width - text_width) // 2
        text_y = (height - text_height) // 2

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
