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
        logger.info(f"Received search request for: {q}")
        results = youtube_service.search(q)
        return results
    except RuntimeError as e:
        logger.error(f"Search failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in search: {str(e)}")
        raise HTTPException(status_code=500, detail="Search failed. Please try again.")
