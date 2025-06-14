import azure.functions as func
from azure.functions import Blueprint
from PIL import Image, ImageDraw
from shared.utils.font_utils import load_font
from shared.utils.text_box_utils import calculate_text_box
from shared.fonts import FONT_PATHS
from generated_models.models import ImageContent, VisualStyle, Font, Color, Background, TextOverlay, Container, Format
import io
import traceback

image_generation_blueprint = Blueprint()

@image_generation_blueprint.route(route="generate-image", methods=["POST"])
def generate_image(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
        # Parse using new models
        container = data.get('container', {})
        background = data.get('background', {})
        format_ = data.get('format', {'imageFormat': 'PNG'})
        text_overlay = data.get('textOverlay', {})

        width = int(container.get('width', 1080))
        height = int(container.get('height', 1080))
        container_padding = int(container.get('padding', 0))

        # Background handling
        img = None
        bg_color = None
        bg_type = background.get('type', 'color')
        bg_value = background.get('value', '#FFFFFF')
        bg_filters = background.get('filters', [])
        try:
            if bg_type == 'image' and isinstance(bg_value, str) and (bg_value.startswith('http://') or bg_value.startswith('https://')):
                from urllib.request import urlopen
                from PIL import Image as PILImage, ImageOps, ImageFilter
                with urlopen(bg_value) as response:
                    bg_img = PILImage.open(response).convert('RGBA')
                    # COVER EFFECT: Resize and crop to fill container, maintain aspect ratio
                    bg_img = ImageOps.fit(bg_img, (width, height), method=Image.LANCZOS, centering=(0.5, 0.5))
                    for filter_type in bg_filters:
                        if filter_type == 'grayscale':
                            bg_img = ImageOps.grayscale(bg_img).convert('RGBA')
                        elif filter_type == 'blur':
                            bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=2))
                        elif filter_type == 'contour':
                            bg_img = bg_img.filter(ImageFilter.CONTOUR)
                        elif filter_type == 'edge_enhance':
                            bg_img = bg_img.filter(ImageFilter.EDGE_ENHANCE)
                        elif filter_type == 'sharpen':
                            bg_img = bg_img.filter(ImageFilter.SHARPEN)
                        elif filter_type == 'emboss':
                            bg_img = bg_img.filter(ImageFilter.EMBOSS)
                        elif filter_type == 'invert':
                            bg_img = ImageOps.invert(bg_img.convert('RGB')).convert('RGBA')
                        elif filter_type == 'sepia':
                            gray = ImageOps.grayscale(bg_img)
                            sepia = ImageOps.colorize(gray, '#704214', '#C0C080')
                            bg_img = sepia.convert('RGBA')
                    img = bg_img.copy()
            elif bg_type == 'color' and isinstance(bg_value, str) and bg_value.startswith('#'):
                bg_color = bg_value
            else:
                bg_color = bg_value or '#FFFFFF'
        except Exception as e:
            print(f"[ImageGen] Exception in background processing: {e}")
            bg_color = '#FFFFFF'

        if img is None:
            # Fallback to color background
            if bg_color and bg_color.startswith('#'):
                lv = len(bg_color) - 1
                rgb = tuple(int(bg_color[i:i+lv//3], 16) for i in range(1, lv+1, lv//3))
            else:
                rgb = (255, 255, 255)
            img = Image.new("RGBA", (width, height), rgb + (255,))

        draw = ImageDraw.Draw(img, "RGBA")

        # Text overlay
        text = text_overlay.get('text', '')
        visual_style = text_overlay.get('visualStyle', {})
        horizontal_align = text_overlay.get('horizontalAlign', 'center')
        vertical_align = text_overlay.get('verticalAlign', 'middle')

        font = load_font(visual_style)
        # Convert color fields to tuples
        text_color = visual_style.get('color', '#000000')
        if isinstance(text_color, dict):
            text_color = text_color.get('text', '#000000')
        text_color_tuple = hex_to_rgba(text_color, 255) if isinstance(text_color, str) and text_color.startswith('#') else text_color
        outline = visual_style.get('outline', {})
        outline_color = outline.get('color', '#FF0000')
        outline_color_tuple = hex_to_rgba(outline_color, 255) if isinstance(outline_color, str) and outline_color.startswith('#') else outline_color
        outline_width = int(outline.get('width', 1))
        box_color = visual_style.get('box', {}).get('color', '#000000')
        box_alpha = int(visual_style.get('box', {}).get('alpha', 128))

        box_info = calculate_text_box(
            draw=draw,
            text=text,
            font=font,
            container_width=width,
            container_height=height,
            container_padding=container_padding,
            visual_style=visual_style,
            horizontal_align=horizontal_align,
            vertical_align=vertical_align
        )
        x = box_info['x']
        y = box_info['y']

        # Draw box
        if box_color and box_alpha > 0:
            box_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            box_draw = ImageDraw.Draw(box_layer, "RGBA")
            if box_color.startswith('#'):
                lv = len(box_color) - 1
                rgb = tuple(int(box_color[i:i+lv//3], 16) for i in range(1, lv+1, lv//3))
            else:
                rgb = (0, 0, 0)
            box_rgba = rgb + (box_alpha,)
            box_draw.rectangle([
                x, y, x + box_info['box_width'], y + box_info['box_height']
            ], fill=box_rgba)
            img = Image.alpha_composite(img, box_layer)
            draw = ImageDraw.Draw(img, "RGBA")

        # Draw outline and text
        if box_info['horizontal_align'] == 'center':
            text_x = x + (box_info['box_width'] - box_info['text_w']) // 2
        elif box_info['horizontal_align'] == 'right':
            text_x = x + box_info['box_width'] - box_info['text_w'] - box_info['pad_x']
        else:
            text_x = x + box_info['pad_x']
        text_y = y + box_info['pad_y_top']
        if outline_width > 0:
            for ox in range(-outline_width, outline_width + 1):
                for oy in range(-outline_width, outline_width + 1):
                    if ox == 0 and oy == 0:
                        continue
                    draw.multiline_text((text_x + ox, text_y + oy), box_info['wrapped_text'], font=box_info['font'], fill=outline_color_tuple, align=box_info['horizontal_align'])
        draw.multiline_text((text_x, text_y), box_info['wrapped_text'], font=box_info['font'], fill=text_color_tuple, align=box_info['horizontal_align'])

        buf = io.BytesIO()
        img.save(buf, format=format_.get('imageFormat', 'PNG'))
        buf.seek(0)
        return func.HttpResponse(buf.getvalue(), mimetype="image/png")
    except Exception as e:
        print(f"[ImageGen] Exception occurred: {e}")
        traceback.print_exc()
        return func.HttpResponse(f"Error: {str(e)}", status_code=500)

def hex_to_rgba(hex_color, alpha=255):
    hex_color = hex_color.lstrip('#')
    lv = len(hex_color)
    rgb = tuple(int(hex_color[i:i+lv//3], 16) for i in range(0, lv, lv//3))
    if len(rgb) == 3:
        return rgb + (alpha,)
    return rgb
