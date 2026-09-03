"""
Main FastAPI application for AI Portfolio Backend.
Production configuration.
"""

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.chat import router as chat_router
from app.api.project_cards import router as project_cards_router
from app.api.tracking import router as tracking_router
from app.api.case_match import router as case_match_router
from app.api.document_fragment import router as document_fragment_router
from app.api.admin import admin_router
from app.core.config import get_settings


settings = get_settings()

app = FastAPI(
    title="AI Portfolio API",
    description="Backend for AI Portfolio AI Assistant",
    version="0.1.0",
    debug=settings.debug,
)

# CORS middleware - configured via CORS_ORIGINS env var
# CORS_ORIGINS must be set to the actual domain(s), e.g.:
# CORS_ORIGINS=https://ai.alex-n8n.site
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)

# Include routers
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(project_cards_router)
app.include_router(tracking_router)
app.include_router(case_match_router)
app.include_router(document_fragment_router)
app.include_router(admin_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "AI Portfolio API",
        "version": "0.1.0",
        "status": "running"
    }