from typing import Optional, List
from pydantic import BaseModel

class Font(BaseModel):
    family: str
    size: str
    weight: Optional[str] = None
    style: Optional[str] = None

class Color(BaseModel):
    text: str
    background: str
    outline: Optional[str] = None

class Outline(BaseModel):
    color: Optional[str] = None
    width: Optional[int] = None

class Alignment(BaseModel):
    textAlign: Optional[str] = None  # left, center, right

class VisualStyle(BaseModel):
    font: Font
    color: Color
    outline: Optional[Outline] = None
    alignment: Optional[Alignment] = None
    box: Optional[dict] = None

class Container(BaseModel):
    width: Optional[int] = None
    height: Optional[int] = None
    padding: Optional[int] = None

class Background(BaseModel):
    type: str  # 'color' or 'image'
    value: str  # color code or URL/local path
    filters: Optional[List[str]] = None  # Only for type='image'

class Format(BaseModel):
    imageFormat: Optional[str] = None  # png, jpeg

class TextOverlay(BaseModel):
    text: Optional[str] = None
    visualStyle: Optional[VisualStyle] = None
    horizontalAlign: Optional[str] = None  # left, center, right
    verticalAlign: Optional[str] = None    # top, middle, bottom

class ImageContent(BaseModel):
    container: Optional[Container] = None
    background: Optional[Background] = None
    format: Optional[Format] = None
    textOverlay: Optional[TextOverlay] = None
