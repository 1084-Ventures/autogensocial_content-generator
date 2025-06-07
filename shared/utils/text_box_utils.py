"""
text_box_utils.py

Utilities for calculating and drawing text boxes on images, ensuring that text
is wrapped, resized, and (if necessary) truncated so it fits neatly within a
specified container area.

Functions:
    - calculate_text_box: Determine wrapped text, box dimensions, and placement.
    - draw_text_box: Render a semi-transparent background box and draw the text.
"""

from PIL import ImageDraw, ImageFont
import textwrap
from shared.utils.font_utils import load_font


def calculate_text_box(draw, text, font, container_width, container_height,
                       container_padding=0, min_font_size=10, visual_style=None, settings_path=None,
                       max_box_width_pct=0.8, max_box_height_pct=0.8,
                       horizontal_align='center', vertical_align='middle'):
    """
    Calculate a text box that fits within a container area by wrapping, resizing,
    and truncating text as needed. Returns wrapped text, dimensions, placement, and
    the (potentially resized) font object.

    Parameters:
        draw (PIL.ImageDraw.Draw): An ImageDraw.Draw instance used for measurements.
        text (str): The text to render.
        font (PIL.ImageFont.FreeTypeFont): Initial font to use.
        container_width (int): Width of the container area (pixels).
        container_height (int): Height of the container area (pixels).
        container_padding (int): Padding inside the container (pixels).
        min_font_size (int): Smallest font size to which text may shrink.
        visual_style (str): Optional visual style identifier for loading fonts.
        settings_path (str): Optional path to settings for loading fonts.
        max_box_width_pct (float): Max width of box as percent of container (default 0.8).
        max_box_height_pct (float): Max height of box as percent of container (default 0.8).
        horizontal_align (str): 'left', 'center', or 'right'.
        vertical_align (str): 'top', 'middle', or 'bottom'.

    Returns:
        dict: Box info and layout details.

    Notes:
        - The function first attempts to wrap lines so the box_width ≤ max_box_width.
        - If wrapping alone cannot fit the text (either width or height), it reduces
          the font size one point at a time down to `min_font_size`.
        - If, at `min_font_size`, the box is still too tall, the text is truncated
          with an ellipsis on the last visible line.
        - The returned (x, y) center the box within the padded container area.
    """
    # Retrieve font metrics for consistent height calculation
    ascent, descent = font.getmetrics()

    def measure(txt, fnt):
        """
        Measure the pixel width and height of `txt` when drawn with `fnt`.
        Returns (w, h). If `textbbox` is unavailable, falls back to getsize().
        """
        try:
            bbox = draw.textbbox((0, 0), txt, font=fnt)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            # Add descent to height to include letters like y/g/p
            ascent, descent = fnt.getmetrics()
            h += descent
        except AttributeError:
            w, h = fnt.getsize(txt)
            ascent, descent = fnt.getmetrics()
            h += descent
        return w, h

    # Determine available space inside the container (now as a percentage)
    available_width = container_width - 2 * container_padding
    available_height = container_height - 2 * container_padding
    max_box_width = available_width  # Use full available width, not a percentage
    max_box_height = int(available_height * max_box_height_pct)

    # Calculate padding as a percentage of the text size (dynamic, but box cannot exceed container)
    def get_dynamic_padding(text_w, text_h):
        pad_x = max(int(text_w * 0.05), 10)
        pad_y = max(int(text_h * 0.05), 10)
        return pad_x, pad_y

    def wrap_text_to_width(text, font, max_width):
        lines = []
        for paragraph in text.split('\n'):
            words = paragraph.split()
            if not words:
                lines.append('')
                continue
            line = words[0]
            for word in words[1:]:
                test_line = f"{line} {word}"
                try:
                    bbox = draw.textbbox((0, 0), test_line, font=font)
                    w = bbox[2] - bbox[0]
                except AttributeError:
                    w, _ = font.getsize(test_line)
                if w <= max_width:
                    line = test_line
                else:
                    lines.append(line)
                    line = word
            lines.append(line)
        return '\n'.join(lines)

    # Initial wrap to container width
    wrapped_text = wrap_text_to_width(text, font, max_box_width - 2 * 10)
    text_w, text_h = measure(wrapped_text, font)
    pad_x, pad_y = get_dynamic_padding(text_w, text_h)
    pad_y_top = pad_y_bottom = pad_y
    box_width = text_w + 2 * pad_x
    box_height = text_h + pad_y_top + pad_y_bottom

    # If box exceeds container, shrink padding and/or truncate
    if box_width > max_box_width:
        pad_x = max((max_box_width - text_w) // 2, 0)
        box_width = text_w + 2 * pad_x
    if box_height > max_box_height:
        pad_y = max((max_box_height - text_h) // 2, 0)
        box_height = text_h + 2 * pad_y

    # If height still exceeds max, truncate lines with ellipsis
    if box_height > max_box_height:
        lines = wrapped_text.split('\n')
        single_h = text_h // max(1, len(lines))
        allowable_text_height = max_box_height - 2 * pad_y
        max_lines = max(int(allowable_text_height / single_h), 1)
        truncated = lines[:max_lines]
        if truncated:
            last_line = truncated[-1]
            if len(last_line) > 3:
                truncated[-1] = last_line[:-3] + '...'
            else:
                truncated[-1] = '...'
        wrapped_text = '\n'.join(truncated)
        text_w, text_h = measure(wrapped_text, font)
        pad_x, pad_y = get_dynamic_padding(text_w, text_h)
        box_width = text_w + 2 * pad_x
        box_height = text_h + 2 * pad_y
        # Ensure box does not exceed container
        if box_width > max_box_width:
            pad_x = max((max_box_width - text_w) // 2, 0)
            box_width = text_w + 2 * pad_x
        if box_height > max_box_height:
            pad_y = max((max_box_height - text_h) // 2, 0)
            box_height = text_h + 2 * pad_y

    # Calculate x position based on horizontal_align
    available_width = container_width - 2 * container_padding
    available_height = container_height - 2 * container_padding
    if horizontal_align == 'left':
        x = container_padding
    elif horizontal_align == 'right':
        x = container_padding + available_width - box_width
    else:  # center
        x = container_padding + (available_width - box_width) // 2
    if x < container_padding:
        x = container_padding

    # Calculate y position based on vertical_align
    if vertical_align == 'top':
        y = container_padding
    elif vertical_align == 'bottom':
        y = container_padding + available_height - box_height
    else:  # middle
        y = container_padding + (available_height - box_height) // 2
    if y < container_padding:
        y = container_padding

    # Return box location and size
    return {
        'wrapped_text': wrapped_text,
        'text_w': text_w,
        'text_h': text_h,
        'pad_x': pad_x,
        'pad_y_top': pad_y,
        'pad_y_bottom': pad_y,
        'box_width': box_width,
        'box_height': box_height,
        'x': x,
        'y': y,
        'font': font,
        'box_location': {
            'left': x,
            'top': y,
            'right': x + box_width,
            'bottom': y + box_height,
            'center_x': x + box_width // 2,
            'center_y': y + box_height // 2
        },
        'horizontal_align': horizontal_align,
        'vertical_align': vertical_align
    }


def draw_text_box(image, text, font_path, initial_font_size, container_width,
                  container_height, container_padding=0, min_font_size=10, box_color=(0, 0, 0, 180), text_color=(255, 255, 255)):
    """
    Draw a semi-transparent box behind the text and render wrapped/truncated text
    centered within the specified container area.

    Parameters:
        image (PIL.Image.Image): The image on which to draw.
        text (str): The text to render inside the box.
        font_path (str): Path to a TrueType font file (e.g., .ttf).
        initial_font_size (int): Starting font size for rendering.
        container_width (int): Width of the container area (pixels).
        container_height (int): Height of the container area (pixels).
        container_padding (int): Padding inside the container (pixels).
        min_font_size (int): Smallest font size to shrink to.
        box_color (tuple): RGBA color of the box background (e.g., semi-transparent).
        text_color (tuple): RGB color of the rendered text.

    Returns:
        PIL.Image.Image: The same `image` object, with the text box drawn on it.

    Usage Example:
        from PIL import Image
        img = Image.open("background.png").convert("RGBA")
        updated = draw_text_box(
            image=img,
            text="This is a test caption that might be quite long.",
            font_path="/path/to/Arial.ttf",
            initial_font_size=48,
            container_width=img.width,
            container_height=img.height,
            container_padding=20,
            min_font_size=12,
            box_color=(0, 0, 0, 180),
            text_color=(255, 255, 255)
        )
        updated.save("with_caption.png")
    """
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(font_path, initial_font_size)
    (
        wrapped_text,
        text_w,
        text_h,
        pad_x,
        pad_y_top,
        pad_y_bottom,
        box_width,
        box_height,
        x,
        y,
        font
    ) = calculate_text_box(
        draw,
        text,
        font,
        container_width,
        container_height,
        container_padding,
        min_font_size
    )

    # Draw the semi-transparent background rectangle
    box_coords = [x, y, x + box_width, y + box_height]
    draw.rectangle(box_coords, fill=box_color)

    # Draw the wrapped (and possibly truncated) text
    text_x = x + pad_x
    text_y = y + pad_y_top
    draw.multiline_text(
        (text_x, text_y),
        wrapped_text,
        font=font,
        fill=text_color,
        align="left"
    )

    return image
