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

class Container(BaseModel):
    width: Optional[int] = None
    height: Optional[int] = None
    padding: Optional[int] = None

class FormatMinResolution(BaseModel):
    width: Optional[int] = None
    height: Optional[int] = None

class Format(BaseModel):
    minResolution: Optional[FormatMinResolution] = None
    maxFileSize: Optional[int] = None
    imageFormat: Optional[str] = None  # png, jpeg

class TextOverlay(BaseModel):
    text: Optional[str] = None
    visualStyle: Optional[VisualStyle] = None  # Reference to VisualStyle for overlay text and styling
    alignment: Optional[Alignment] = None

class ImageContent(BaseModel):
    container: Optional[Container] = None
    background: Optional[str] = None  # color code or image URL
    backgroundType: Optional[str] = None  # 'color' or 'image'
    format: Optional[Format] = None
    effects: Optional[List[str]] = None
    textOverlay: Optional[TextOverlay] = None
    transparent: Optional[bool] = None
    imageType: Optional[str] = None  # 'portrait', 'landscape', 'square'
