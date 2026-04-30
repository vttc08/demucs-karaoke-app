"""API routes for YouTube search."""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
from models import YouTubeSearchResult
from services.youtube_service import YouTubeService
from services.lyrics_service import LyricsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])
youtube_service = YouTubeService()
lyrics_service = LyricsService()


class MetadataInference(BaseModel):
    title: str
    artist: Optional[str] = None
    source: str


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


@router.get("/infer", response_model=MetadataInference)
async def infer_metadata(
    title: str = Query(..., description="Song title or filename"),
    artist: Optional[str] = Query(None, description="Artist name (optional)"),
):
    """
    Infer/normalize song metadata using LastFM and regex patterns.
    
    Query parameters:
    - title: Song title or filename to parse (required)
    - artist: Artist name hint (optional)
    """
    try:
        logger.info("Metadata inference requested title=%r artist=%r", title, artist)
        inferred = await lyrics_service.infer_song_metadata(title=title, artist=artist)
        return MetadataInference(
            title=inferred.title,
            artist=inferred.artist,
            source=inferred.source,
        )
    except Exception as e:
        logger.exception("Metadata inference failed title=%r artist=%r error=%s", title, artist, str(e))
        raise HTTPException(status_code=500, detail="Metadata inference failed. Please try again.")
