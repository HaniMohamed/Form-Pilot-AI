"""
FastAPI application factory for FormPilot AI.

Creates and configures the FastAPI app, initializes the LLM provider,
session store, LangGraph, and routes.

Run with:
    uvicorn backend.api.app:app --reload
"""

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.memory import MemorySaver

from backend.agent.graph import compile_graph
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


def _is_truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    application = FastAPI(
        title="FormPilot AI",
        description="GenAI Conversational Form Filling System",
        version="0.2.0",
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

    # Initialize LLM (OpenAI-compatible endpoint)
    try:
        llm = get_llm()
        logger.info("LLM initialized: %s", os.getenv("CUSTOM_LLM_API_ENDPOINT", "not set"))
    except Exception as e:
        logger.warning(
            "Failed to initialize LLM: %s. "
            "The /chat endpoint will fail until a valid LLM is configured.",
            e,
        )
        llm = None

    # Compile the LangGraph state machine (once, shared across all sessions).
    # Optional checkpointer helps with replay/debug and future persistence upgrades.
    enable_checkpointer = _is_truthy(os.getenv("ENABLE_LANGGRAPH_CHECKPOINTER"), default=False)
    checkpointer = MemorySaver() if enable_checkpointer else None
    graph = compile_graph(checkpointer=checkpointer)
    logger.info("LangGraph compiled successfully")
    if enable_checkpointer:
        logger.info("LangGraph checkpointer enabled: MemorySaver")

    # Initialize session store
    session_timeout = int(os.getenv("SESSION_TIMEOUT_SECONDS", "1800"))
    session_store = SessionStore(timeout_seconds=session_timeout)

    # Configure routes with dependencies
    configure_routes(session_store, llm, graph)
    application.include_router(router, prefix="/api")

    @application.on_event("startup")
    async def on_startup():
        logger.info("FormPilot AI backend starting up")
        logger.info("LLM endpoint: %s", os.getenv("CUSTOM_LLM_API_ENDPOINT", "not set"))
        logger.info("Session timeout: %d seconds", session_timeout)

    return application


# Create the app instance (used by uvicorn)
app = create_app()
