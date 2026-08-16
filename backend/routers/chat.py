"""
FastAPI Router for VMS Pro AI Surveillance Chatbot & Image Search.
"""

from typing import Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel

from ..auth.helpers import verify_viewer
from ..services.copilot.chat_engine import chat_engine

router = APIRouter(prefix="/chat", tags=["AI Chatbot"])


class ChatMessageRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    mode: Optional[str] = "all"


class NewSessionRequest(BaseModel):
    title: Optional[str] = "New Investigation"


@router.get("/sessions")
def get_chat_sessions(user=Depends(verify_viewer)):
    username = getattr(user, "username", None) or (user.get("username") if isinstance(user, dict) else "operator")
    sessions = chat_engine.list_sessions(username=username)
    return {"sessions": sessions}


@router.post("/session/new")
def create_new_chat_session(payload: Optional[NewSessionRequest] = None, user=Depends(verify_viewer)):
    new_uuid = f"chat_{uuid.uuid4().hex[:10]}"
    title = payload.title if payload and payload.title else "New Investigation"
    return {"session_id": new_uuid, "title": title}


@router.delete("/session/{session_id}")
def delete_chat_session(session_id: str, user=Depends(verify_viewer)):
    username = getattr(user, "username", None) or (user.get("username") if isinstance(user, dict) else "operator")
    success = chat_engine.delete_session(session_id, username=username)
    return {"success": success, "session_id": session_id}


@router.post("/message")
def post_chat_message(
    payload: ChatMessageRequest,
    user=Depends(verify_viewer)
):
    if not payload.query or not payload.query.strip():
        raise HTTPException(status_code=400, detail="Message query text cannot be empty.")
    
    username = getattr(user, "username", None) or (user.get("username") if isinstance(user, dict) else "operator")
    res = chat_engine.process_text_query(
        user_query=payload.query,
        session_uuid=payload.session_id,
        username=username,
        search_mode=payload.mode or "all"
    )
    return res


@router.post("/upload-search")
async def post_upload_search(
    file: UploadFile = File(...),
    query: Optional[str] = Form(default=None),
    session_id: Optional[str] = Form(default=None),
    mode: Optional[str] = Form(default="all"),
    user=Depends(verify_viewer)
):
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded image file is empty.")

    username = getattr(user, "username", None) or (user.get("username") if isinstance(user, dict) else "operator")
    res = chat_engine.process_image_query(
        image_bytes=contents,
        user_query=query,
        session_uuid=session_id,
        username=username,
        search_mode=mode or "all"
    )
    return res


@router.get("/history")
def get_chat_history(
    session_id: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
    before_id: Optional[int] = Query(default=None),
    user=Depends(verify_viewer)
):
    res = chat_engine.get_history(session_id, limit=limit, before_id=before_id)
    return {"session_id": session_id, **res}


@router.get("/suggestions")
def get_chat_suggestions(user=Depends(verify_viewer)):
    return {
        "suggestions": [
            "Koi blue color ka shirt wala banda station pr dikha tha kya?",
            "Laal color ki car spot hui kya gate ke paas?",
            "Bina helmet motorcycle chalane wala koi mila?",
            "Is there any blue shirt guy anywhere found?",
            "Where was license plate KA51MB8811 spotted?"
        ]
    }
