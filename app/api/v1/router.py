from fastapi import APIRouter

from app.api.v1.ask import router as ask_router
from app.api.v1.conversations import router as conversation_router
from app.api.v1.documents import router as document_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.ingest_jobs import router as ingest_router
from app.api.v1.kb import router as kb_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(kb_router)
api_router.include_router(document_router)
api_router.include_router(ingest_router)
api_router.include_router(ask_router)
api_router.include_router(conversation_router)
api_router.include_router(feedback_router)
