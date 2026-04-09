"""API routes for YouTube search."""
import logging
from typing import List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import YouTubeSearchResult
from services.youtube_service import YouTubeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])
youtube_service = YouTubeService()


@router.get("/", response_model=List[YouTubeSearchResult])
async def search_youtube(
    q: str = Query(..., description="Search query"),
    source: str | None = Query(None, description="Filter by source: 'local', 'youtube', or omit for both"),
    db: Session = Depends(get_db),
):
    """
    Search YouTube and/or local library for videos.
    
    Query parameters:
    - q: Search query (required)
    - source: Optional filter - "local" for local library only, "youtube" for YouTube only, omit for both
    """
    # Validate source parameter
    if source is not None and source not in ("local", "youtube"):
        raise HTTPException(
            status_code=400,
            detail="source must be 'local' or 'youtube'"
        )
    
    try:
        logger.info("Search requested query=%r source=%r", q, source)
        results = youtube_service.search(q, source=source, db=db)
        return results
    except RuntimeError as e:
        logger.error("Search failed query=%r source=%r error=%s", q, source, str(e))
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected search error query=%r source=%r error=%s", q, source, str(e))
        raise HTTPException(status_code=500, detail="Search failed. Please try again.")
