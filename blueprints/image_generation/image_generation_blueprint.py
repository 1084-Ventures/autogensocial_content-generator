import azure.functions as func
from azure.functions import Blueprint
import json
from PIL import Image, ImageDraw, ImageFont
import io
from shared.fonts import FONT_PATHS
import textwrap

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
        # Transparency
        text_alpha = int(color.get("textAlpha", 255))
        # Image layout
        width = image.get("container", {}).get("width", 800)
        height = image.get("container", {}).get("height", 600)
        box_height = 80
        # Background image support
        background_image_path = image.get("background")
        img = None
        if background_image_path:
            try:
                if background_image_path.startswith("http://") or background_image_path.startswith("https://"):
                    import requests
                    resp = requests.get(background_image_path)
                    bg_img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                else:
                    bg_img = Image.open(background_image_path).convert("RGB")
                # Center the background image on the canvas without resizing
                img = Image.new("RGB", (width, height), bg_color)
                bg_w, bg_h = bg_img.size
                x = (width - bg_w) // 2
                y = (height - bg_h) // 2
                img.paste(bg_img, (x, y))
            except Exception as e:
                img = Image.new("RGB", (width, height), bg_color)
        else:
            img = Image.new("RGB", (width, height), bg_color)
        draw = ImageDraw.Draw(img, "RGBA")
        # Draw the box below the image only if boxText is provided
        box_text = data.get("boxText", "")
        if box_text:
            # Expand image to fit box
            new_img = Image.new("RGB", (width, height + box_height), bg_color)
            new_img.paste(img, (0, 0))
            draw = ImageDraw.Draw(new_img, "RGBA")
            draw.rectangle([0, height, width, height + box_height], fill=box_color)
            img = new_img
        # Load font using FONT_PATHS, supporting Azure Blob Storage with connection string
        import os
        from urllib.parse import unquote
        # --- Font selection logic update ---
        def get_font_url_from_paths(font_family, font_weight, font_style):
            # Normalize style keys
            style_key = "regular"
            if font_weight == "bold" and font_style == "italic":
                style_key = "bold_italic"
            elif font_weight == "bold":
                style_key = "bold"
            elif font_style == "italic":
                style_key = "italic"
            # Get font entry from FONT_PATHS
            font_entry = FONT_PATHS.get(font_family)
            if isinstance(font_entry, dict):
                # Try requested style
                if style_key in font_entry:
                    return font_entry[style_key]
                # Fallbacks
                if "regular" in font_entry:
                    return font_entry["regular"]
                # Any available style
                for v in font_entry.values():
                    return v
            elif isinstance(font_entry, str):
                return font_entry
            return None

        font_url = get_font_url_from_paths(font_family, font_weight, font_style)
        try:
            if font_url:
                if font_url.startswith("http://") or font_url.startswith("https://"):
                    from azure.storage.blob import BlobServiceClient
                    from urllib.parse import urlparse
                    parsed = urlparse(font_url)
                    path_parts = parsed.path.lstrip('/').split('/', 1)
                    container = path_parts[0]
                    blob = unquote(path_parts[1])
                    conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
                    if not conn_str:
                        raise Exception("AZURE_STORAGE_CONNECTION_STRING environment variable not set")
                    blob_service_client = BlobServiceClient.from_connection_string(conn_str)
                    blob_client = blob_service_client.get_blob_client(container=container, blob=blob)
                    font_bytes = io.BytesIO()
                    download_stream = blob_client.download_blob()
                    font_bytes.write(download_stream.readall())
                    font_bytes.seek(0)
                    font = ImageFont.truetype(font_bytes, font_size)
                else:
                    font = ImageFont.truetype(font_url, font_size)
            else:
                font = ImageFont.truetype("arial.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()
        # --- Improved word wrapping and alignment logic ---
        def wrap_text(text, font, max_width, draw):
            words = text.split()
            lines = []
            current_line = ''
            for word in words:
                test_line = current_line + (' ' if current_line else '') + word
                width = draw.textlength(test_line, font=font)
                if width <= max_width:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)
            return lines

        def get_text_block_size(lines, font, draw):
            line_heights = []
            line_widths = []
            for line in lines:
                bbox = font.getbbox(line)
                line_width = bbox[2] - bbox[0]
                line_height = bbox[3] - bbox[1]
                line_widths.append(draw.textlength(line, font=font))
                line_heights.append(line_height)
            total_height = sum(line_heights)
            max_width = max(line_widths) if line_widths else 0
            return max_width, total_height, line_heights

        max_text_width = width - 20  # 10px padding on each side
        lines = wrap_text(text, font, max_text_width, draw)
        text_block_width, total_text_height, line_heights = get_text_block_size(lines, font, draw)
        # Optionally shrink font size if text block is too tall
        min_font_size = 12
        while total_text_height > height - 20 and font.size > min_font_size:
            font = ImageFont.truetype(font.path, font.size - 2) if hasattr(font, 'path') else font.font_variant(size=font.size - 2)
            lines = wrap_text(text, font, max_text_width, draw)
            text_block_width, total_text_height, line_heights = get_text_block_size(lines, font, draw)
        # Center text block vertically
        text_y = (height - total_text_height) // 2
        # Draw box behind main text if textBox is provided
        text_box = data.get("textBox", {})
        if text_box:
            box_color = text_box.get("color", "#FFFFFF")
            box_alpha = int(text_box.get("alpha", 255))
            box_outline_color = text_box.get("outlineColor")
            box_outline_width = int(text_box.get("outlineWidth", 0))
            box_padding = int(text_box.get("padding", 10))
            def hex_to_rgba(hex_color, alpha=255):
                hex_color = hex_color.lstrip('#')
                lv = len(hex_color)
                rgb = tuple(int(hex_color[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))
                return (*rgb, alpha)
            box_rgba = hex_to_rgba(box_color, box_alpha)
            rect_x0 = (width - text_block_width) // 2 - box_padding
            rect_y0 = text_y - box_padding
            rect_x1 = (width + text_block_width) // 2 + box_padding
            rect_y1 = text_y + total_text_height + box_padding
            draw.rectangle([rect_x0, rect_y0, rect_x1, rect_y1], fill=box_rgba)
            if box_outline_color and box_outline_width > 0:
                outline_rgba = hex_to_rgba(box_outline_color, box_alpha)
                for i in range(box_outline_width):
                    draw.rectangle([
                        rect_x0 - i, rect_y0 - i, rect_x1 + i, rect_y1 + i
                    ], outline=outline_rgba)
        # Draw main text with improved alignment
        def hex_to_rgba(hex_color, alpha=255):
            hex_color = hex_color.lstrip('#')
            lv = len(hex_color)
            rgb = tuple(int(hex_color[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))
            return (*rgb, alpha)
        rgba_text_color = hex_to_rgba(text_color, text_alpha)
        if outline_color:
            rgba_outline_color = hex_to_rgba(outline_color, text_alpha)
        else:
            rgba_outline_color = None
        y = text_y
        for i, line in enumerate(lines):
            line_width = draw.textlength(line, font=font)
            if text_align == "left":
                text_x = 10
            elif text_align == "right":
                text_x = width - line_width - 10
            else:  # center
                text_x = (width - line_width) // 2
            draw.text(
                (text_x, y),
                line,
                fill=rgba_text_color,
                font=font,
                stroke_width=outline_width if outline_color else 0,
                stroke_fill=rgba_outline_color if outline_color else None
            )
            y += line_heights[i]
        # Draw box text if provided
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
                stroke_fill=rgba_outline_color if outline_color else None
            )
        # Save to bytes
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        return func.HttpResponse(body=img_bytes.read(), mimetype="image/png", status_code=200)
    except Exception as e:
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")
