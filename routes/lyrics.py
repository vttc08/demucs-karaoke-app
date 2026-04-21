"""API routes for lyrics resolution."""
import logging
from fastapi import APIRouter, HTTPException

from models import LyricsResolveRequest, LyricsResolveResponse
from services.lyrics_service import LyricsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lyrics", tags=["lyrics"])
lyrics_service = LyricsService()


@router.post("/resolve", response_model=LyricsResolveResponse)
async def resolve_lyrics(request: LyricsResolveRequest):
    """Resolve lyrics for the queue modal."""
    try:
        logger.info(
            "Lyrics resolve requested title=%r artist=%r youtube_title=%r",
            request.title,
            request.artist,
            request.youtube_title,
        )
        payload = await lyrics_service.resolve_lyrics(
            title=request.title,
            artist=request.artist,
            youtube_title=request.youtube_title,
        )
    except Exception as exc:
        logger.exception("Lyrics resolve failed title=%r artist=%r", request.title, request.artist)
        raise HTTPException(status_code=500, detail="Lyrics resolution failed") from exc

    if payload is None:
        inferred = await lyrics_service.infer_song_metadata(
            title=request.youtube_title or request.title,
            artist=request.artist,
        )
        return LyricsResolveResponse(
            status="not_found",
            title=inferred.title,
            artist=inferred.artist,
            source=inferred.source,
            detail="Lyrics not found",
        )

    return LyricsResolveResponse(
        status="resolved",
        title=payload.inferred_song.title,
        artist=payload.inferred_song.artist,
        source=payload.inferred_song.source,
        provider=payload.provider,
        lyrics=payload.lyrics,
        is_synced=payload.is_synced,
    )
