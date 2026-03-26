"""API routes for YouTube search."""
import logging
from typing import List
from fastapi import APIRouter, Query, HTTPException
from models import YouTubeSearchResult
from services.youtube_service import YouTubeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])
youtube_service = YouTubeService()


@router.get("/", response_model=List[YouTubeSearchResult])
async def search_youtube(q: str = Query(..., description="Search query")):
    """Search YouTube for videos."""
    try:
        logger.info("YouTube search requested query=%r", q)
        results = youtube_service.search(q)
        return results
    except RuntimeError as e:
        logger.error("YouTube search failed query=%r error=%s", q, str(e))
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected search error query=%r error=%s", q, str(e))
        raise HTTPException(status_code=500, detail="Search failed. Please try again.")
