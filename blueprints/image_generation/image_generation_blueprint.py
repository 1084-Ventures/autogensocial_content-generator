import azure.functions as func
from azure.functions import Blueprint
from PIL import Image, ImageDraw
from shared.utils.font_utils import load_font
from shared.utils.text_box_utils import calculate_text_box
from shared.fonts import FONT_PATHS
from shared.models.image import ImageContent, VisualStyle, Font, Color
import textwrap
import io

image_generation_blueprint = Blueprint()

@image_generation_blueprint.route(route="generate-image", methods=["POST"])
def generate_image(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
        # Simplified input fields
        text = data.get('text', '')
        visual_style = data.get('visualStyle', {})
        container = data.get('container', {})
        # Ensure container is a dict (not a string)
        if not isinstance(container, dict):
            print(f"[ImageGen] Warning: container is not a dict, got {type(container)}. Resetting to empty dict.")
            container = {}
        width = int(container.get('width', 1080))
        height = int(container.get('height', 1080))
        background = data.get('background', '#FFFFFF')
        format_ = data.get('format', {'imageFormat': 'PNG'})

        # Determine background type and create image
        img = None
        bg_color = None
        try:
            if isinstance(background, str) and (background.startswith('http://') or background.startswith('https://')):
                print(f"[ImageGen] Attempting to load background image from URL: {background}")
                from urllib.request import urlopen
                from PIL import Image as PILImage, ImageOps, ImageFilter
                try:
                    with urlopen(background) as response:
                        bg_img = PILImage.open(response).convert('RGBA')
                        bg_img = bg_img.resize((width, height), PILImage.LANCZOS)
                        # Apply filters if specified
                        filters = data.get('backgroundFilters', [])
                        if isinstance(filters, str):
                            filters = [filters]
                        for filter_type in filters:
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
                        print(f"[ImageGen] Loaded and resized background image from URL with filters: {filters}")
                except Exception as e:
                    print(f"[ImageGen] Failed to load background image from URL: {e}")
                    bg_color = '#FFFFFF'
            elif isinstance(background, str) and background.startswith('#'):
                bg_color = background
            else:
                bg_color = background or '#FFFFFF'
        except Exception as e:
            print(f"[ImageGen] Exception in background processing: {e}")
            bg_color = '#FFFFFF'

        if img is None:
            # Fallback to color background (no transparency option)
            if bg_color and bg_color.startswith('#'):
                lv = len(bg_color) - 1
                rgb = tuple(int(bg_color[i:i+lv//3], 16) for i in range(1, lv+1, lv//3))
            else:
                rgb = (255, 255, 255)
            img = Image.new("RGBA", (width, height), rgb + (255,))
            print(f"[ImageGen] Created color background: {rgb + (255,)}")

        draw = ImageDraw.Draw(img, "RGBA")

        # Use shared font_utils to load font
        font = load_font(visual_style)

        # Text color
        text_color = visual_style.get('color', '#000000')
        # Outline
        outline = visual_style.get('outline', {})
        outline_color = outline.get('color', '#FF0000')
        outline_width = int(outline.get('width', 1))
        # Box color
        box_color = visual_style.get('box', {}).get('color', '#000000')
        box_alpha = int(visual_style.get('box', {}).get('alpha', 128))

        # Calculate text box and wrapping using text_box_utils
        container_padding = int(container.get('padding', 0))
        # Use new dict-based API from calculate_text_box
        box_info = calculate_text_box(
            draw=draw,
            text=text,
            font=font,
            container_width=width,
            container_height=height,
            container_padding=container_padding,
            visual_style=visual_style,
            horizontal_align=visual_style.get('horizontalAlign', 'center'),
            vertical_align=visual_style.get('verticalAlign', 'middle')
        )
        print(f"[ImageGen] Box info: {box_info}")

        # Use alignment/location from box_info only (no location override)
        x = box_info['x']
        y = box_info['y']
        print(f"[ImageGen] Final box position: ({{x}}, {{y}}), text position: ({{x + box_info['pad_x']}}, {{y + box_info['pad_y_top']}})")

        # Draw box
        if box_color and box_alpha > 0:
            # Draw the box on a separate transparent layer, then alpha-composite it
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
            draw = ImageDraw.Draw(img, "RGBA")  # Recreate draw for the new image
            print(f"[ImageGen] Drew box with color: {box_rgba} using alpha composite")

        # Draw outline
        # Adjust text_x for alignment
        if box_info['horizontal_align'] == 'center':
            text_x = x + (box_info['box_width'] - box_info['text_w']) // 2
        elif box_info['horizontal_align'] == 'right':
            text_x = x + box_info['box_width'] - box_info['text_w'] - box_info['pad_x']
        else:  # left
            text_x = x + box_info['pad_x']
        text_y = y + box_info['pad_y_top']
        if outline_width > 0:
            for ox in range(-outline_width, outline_width + 1):
                for oy in range(-outline_width, outline_width + 1):
                    if ox == 0 and oy == 0:
                        continue
                    draw.multiline_text((text_x + ox, text_y + oy), box_info['wrapped_text'], font=box_info['font'], fill=outline_color, align=box_info['horizontal_align'])
            print(f"[ImageGen] Drew outline with color: {outline_color}, width: {outline_width}")
        draw.multiline_text((text_x, text_y), box_info['wrapped_text'], font=box_info['font'], fill=text_color, align=box_info['horizontal_align'])
        print(f"[ImageGen] Drew text at: ({{text_x}}, {{text_y}}) with color: {{text_color}} and align: {{box_info['horizontal_align']}}")

        buf = io.BytesIO()
        img.save(buf, format=format_.get('imageFormat', 'PNG'))
        buf.seek(0)
        print(f"[ImageGen] Image saved to buffer, returning response.")
        return func.HttpResponse(buf.getvalue(), mimetype="image/png")
    except Exception as e:
        import traceback
        print(f"[ImageGen] Exception occurred: {e}")
        traceback.print_exc()
        return func.HttpResponse(f"Error: {str(e)}", status_code=500)
