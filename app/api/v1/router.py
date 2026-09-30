"""
Single aggregation point for all v1 routes. This project is RAG-only;
there is no agents.router here by design (see AGENTS.md / README.md).
"""
from fastapi import APIRouter

from app.api.v1.endpoints import auth, documents, search, users 

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(documents.router)
api_router.include_router(search.router)

# Future, once implemented — kept here as a visible roadmap:
# from app.api.v1.endpoints import rag, evaluation, multimodal
# api_router.include_router(rag.router)
# api_router.include_router(evaluation.router)
# api_router.include_router(multimodal.router)
