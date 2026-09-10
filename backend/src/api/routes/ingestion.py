"""
Ingestion Routes
===============

API endpoints for managing news article ingestion:
- POST /api/ingest             - Trigger manual ingestion (+ auto-summarize)
- POST /api/ingest/summarize-pending - Run summarizer over un-summarized rows
- GET  /api/ingest/status      - Get latest ingestion status
- GET  /api/ingest/stats       - Get ingestion statistics
"""

import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Body
from pydantic import BaseModel

from src.database.base import get_db
from src.services.ingestion_service import IngestionService
from src.services.summarization_orchestrator import SummarizationOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingestion"])

# Latest ingestion result (in-process; OK for a single uvicorn worker).
latest_ingestion_result = None


class IngestRequest(BaseModel):
    """Request model for ingestion endpoint."""
    sources: Optional[List[Dict[str, str]]] = None
    background: bool = True
    auto_summarize: bool = True


class IngestResponse(BaseModel):
    """Response model for ingestion endpoint."""
    message: str
    job_id: Optional[str] = None
    background: bool


class IngestStatusResponse(BaseModel):
    """Response model for ingestion status endpoint."""
    status: str
    result: Optional[Dict[str, Any]] = None


@router.post("/", response_model=IngestResponse)
async def trigger_ingestion(
    request: IngestRequest = Body(...),
    background_tasks: BackgroundTasks = None,
    db=Depends(get_db),
):
    """
    Trigger news article ingestion from configured RSS feeds. After ingestion
    completes (background or foreground), articles missing AI summaries are
    fed through the SummarizationOrchestrator unless auto_summarize is False.
    """
    try:
        ingestion_service = IngestionService(db)

        if request.background and background_tasks:
            background_tasks.add_task(
                _run_ingestion,
                ingestion_service,
                request.sources,
                request.auto_summarize,
            )
            return IngestResponse(
                message="Ingestion started in background",
                job_id="bg_ingest_001",
                background=True,
            )

        # Foreground path
        result = ingestion_service.ingest_all(request.sources)
        ingestion_service.close()

        global latest_ingestion_result
        latest_ingestion_result = result

        summary_msg = ""
        if request.auto_summarize and result.total_articles_saved > 0:
            try:
                orchestrator = SummarizationOrchestrator()
                summ_result = await orchestrator.run_pending(limit=20)
                summary_msg = (
                    f"; summarized {summ_result.summarized}/"
                    f"{summ_result.requested}"
                )
            except Exception as exc:
                logger.error(
                    "Foreground summarization failed: %s", exc, exc_info=True
                )
                summary_msg = "; summarization failed (see logs)"

        return IngestResponse(
            message=(
                f"Ingestion completed: {result.total_articles_saved} articles "
                f"saved{summary_msg}"
            ),
            background=False,
        )

    except Exception as exc:
        logger.error("Ingestion failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Ingestion failed: {exc}"
        )


@router.post("/summarize-pending")
async def summarize_pending(limit: int = 50):
    """
    Run the summarization orchestrator over articles still missing an AI
    summary. Use this for backfill or as a manual trigger when ingestion was
    started with auto_summarize=False.
    """
    try:
        orchestrator = SummarizationOrchestrator()
        result = await orchestrator.run_pending(limit=limit)
        return {"success": True, "result": result.to_dict()}
    except Exception as exc:
        logger.error("summarize-pending failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to run summarization: {exc}"
        )


@router.get("/status", response_model=IngestStatusResponse)
async def get_ingestion_status():
    """Get the status of the latest ingestion operation."""
    global latest_ingestion_result
    if latest_ingestion_result is None:
        return IngestStatusResponse(status="no_ingestion_run", result=None)
    return IngestStatusResponse(
        status=latest_ingestion_result.status.value,
        result=latest_ingestion_result.to_dict(),
    )


@router.get("/stats")
async def get_ingestion_stats(db=Depends(get_db)):
    """Get ingestion statistics from the database."""
    try:
        ingestion_service = IngestionService(db)
        stats = ingestion_service.get_stats()
        ingestion_service.close()
        return stats
    except Exception as exc:
        logger.error("Failed to get stats: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to get stats: {exc}"
        )


async def _run_ingestion(
    service: IngestionService,
    sources: Optional[List[Dict[str, str]]],
    auto_summarize: bool = True,
    summarize_limit: int = 20,
):
    """
    Background task: run ingestion, then (optionally) summarize new articles.

    Summarization runs only after a successful ingest that actually saved
    new articles. Failures here are logged but do not propagate, so a broken
    Ollama install never masks an otherwise-good ingestion run.
    """
    global latest_ingestion_result
    try:
        result = service.ingest_all(sources)
        latest_ingestion_result = result
        logger.info("Background ingestion completed: %s", result.to_dict())
    except Exception as exc:
        logger.error("Background ingestion failed: %s", exc, exc_info=True)
        try:
            service.close()
        finally:
            return
    else:
        service.close()

    if not auto_summarize or result.total_articles_saved <= 0:
        return

    try:
        orchestrator = SummarizationOrchestrator()
        summ_result = await orchestrator.run_pending(limit=summarize_limit)
        logger.info(
            "Post-ingest summarization complete: %s", summ_result.to_dict()
        )
    except Exception as exc:
        logger.error("Post-ingest summarization failed: %s", exc, exc_info=True)
