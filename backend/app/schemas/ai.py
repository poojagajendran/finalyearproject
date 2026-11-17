from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class ChatMessage(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant|system)$")
    content: str

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_history: Optional[List[ChatMessage]] = Field(default_factory=list)
    active_group_id: Optional[str] = None

class ToolCallRecord(BaseModel):
    tool_name: str
    args: Dict[str, Any]
    output: Any

class ChatResponse(BaseModel):
    reply: str
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    suggested_actions: Optional[List[str]] = Field(default_factory=list)
    ui_card: Optional[Dict[str, Any]] = None  # e.g., product card, group status card, resolution proposal
