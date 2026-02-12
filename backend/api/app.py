"""
FastAPI application factory for FormPilot AI.

Creates and configures the FastAPI app, initializes the LLM provider,
session store, and routes.

Run with:
    uvicorn backend.api.app:app --reload
"""

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.agent.llm_provider import get_llm
from backend.api.routes import configure_routes, router
from backend.core.session import SessionStore

# Load environment variables from .env
load_dotenv()

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    application = FastAPI(
        title="FormPilot AI",
        description="GenAI Conversational Form Filling System",
        version="0.1.0",
    )

    # CORS — allow all origins in development
    allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize LLM provider
    provider = os.getenv("LLM_PROVIDER", "openai")
    try:
        llm = get_llm(provider)
        logger.info("LLM provider initialized: %s", provider)
    except Exception as e:
        logger.warning(
            "Failed to initialize LLM provider '%s': %s. "
            "The /chat endpoint will fail until a valid LLM is configured.",
            provider,
            e,
        )
        llm = None

    # Initialize session store
    session_timeout = int(os.getenv("SESSION_TIMEOUT_SECONDS", "1800"))
    session_store = SessionStore(timeout_seconds=session_timeout)

    # Configure routes with dependencies
    configure_routes(session_store, llm)
    application.include_router(router, prefix="/api")

    @application.on_event("startup")
    async def on_startup():
        logger.info("FormPilot AI backend starting up")
        logger.info("LLM Provider: %s", provider)
        logger.info("Session timeout: %d seconds", session_timeout)

    return application


# Create the app instance (used by uvicorn)
app = create_app()
