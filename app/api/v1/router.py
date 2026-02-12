from fastapi import APIRouter

from app.api.v1.ask import router as ask_router
from app.api.v1.auth import router as auth_router
from app.api.v1.conversations import router as conversation_router
from app.api.v1.documents import router as document_router
from app.api.v1.eval import router as eval_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.ingest_jobs import router as ingest_router
from app.api.v1.kb import router as kb_router
from app.api.v1.monitor import router as monitor_router
from app.api.v1.roles import router as role_router
from app.api.v1.users import router as user_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(kb_router)
api_router.include_router(document_router)
api_router.include_router(ingest_router)
api_router.include_router(ask_router)
api_router.include_router(conversation_router)
api_router.include_router(feedback_router)
api_router.include_router(eval_router)
api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(role_router)
api_router.include_router(monitor_router)
