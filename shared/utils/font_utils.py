import os
import json
from PIL import ImageFont
from shared.fonts import FONT_PATHS
from shared.utils.azure_blob_utils import download_blob_to_bytes

def resolve_font_path(visual_style):
    font_family = visual_style.get('font', {}).get('family', 'Arial')
    font_size = int(str(visual_style.get('font', {}).get('size', '32px')).replace('px', ''))
    font_path = FONT_PATHS.get(font_family, '/Library/Fonts/Arial.ttf')
    if isinstance(font_path, dict):
        weight = visual_style.get('font', {}).get('weight', 'normal') or 'normal'
        style = visual_style.get('font', {}).get('style', 'normal') or 'normal'
        style_key = 'regular'
        if weight == 'bold' and style == 'italic':
            style_key = 'bold_italic'
        elif weight == 'bold':
            style_key = 'bold'
        elif style == 'italic':
            style_key = 'italic'
        font_path_resolved = font_path.get(style_key) or font_path.get('regular') or next(iter(font_path.values()))
    else:
        font_path_resolved = font_path
    return font_path_resolved, font_size, font_family

def load_font(visual_style, settings_path=None, override_size=None):
    font_path_resolved, font_size, font_family = resolve_font_path(visual_style)
    if override_size is not None:
        font_size = override_size
    font = None
    try:
        if isinstance(font_path_resolved, str) and font_path_resolved.startswith('http'):
            if not settings_path:
                settings_path = os.path.join(os.path.dirname(__file__), '../../local.settings.json')
            with open(settings_path, 'r') as f:
                settings = json.load(f)
            conn_str = settings['Values'].get('AZURE_STORAGE_CONNECTION_STRING')
            if not conn_str or 'UseDevelopmentStorage=true' in conn_str:
                raise Exception("AZURE_STORAGE_CONNECTION_STRING is not set to a real Azure Storage account.")
            font_bytes = download_blob_to_bytes(font_path_resolved, conn_str)
            font = ImageFont.truetype(font_bytes, font_size)
        else:
            font = ImageFont.truetype(font_path_resolved, font_size)
    except Exception as e:
        print(f"[FontUtils] Failed to load font '{font_family}' at '{font_path_resolved}': {e}")
        font = ImageFont.load_default()
    return font
