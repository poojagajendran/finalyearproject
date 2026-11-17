from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.models.user import User
from backend.app.schemas.ai import ChatRequest, ChatResponse
from backend.app.api.deps import get_current_user
from backend.app.services.ai_agent import ai_agent

router = APIRouter(prefix="/ai", tags=["AI Shopping Assistant"])

@router.post("/chat", response_model=ChatResponse)
async def chat_with_agent(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Interactive natural-language shopping assistant endpoint.
    Processes inquiries, executes backend tool calls with user session context,
    and returns conversational responses with action cards.
    """
    return await ai_agent.chat(req, current_user, db)
