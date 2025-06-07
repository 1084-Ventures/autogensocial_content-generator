from typing import Optional, List, Dict
from pydantic import BaseModel

class GenerateTextContentRequest(BaseModel):
    template: Dict
    variableValues: Optional[Dict[str, str]] = None

class GenerateTextContentResponse(BaseModel):
    text: Optional[str] = None
    hashtags: Optional[List[str]] = None
    comment: Optional[str] = None
    error: Optional[str] = None
