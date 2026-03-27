from typing import Literal
from pydantic import BaseModel, Field, model_validator
try:
    from .settings import (
        DEFAULT_DEMUCS_DEVICE,
        DEFAULT_DEMUCS_MODEL,
        DEFAULT_MP3_BITRATE,
        DEFAULT_OUTPUT_FORMAT,
    )
except ImportError:
    from settings import (
        DEFAULT_DEMUCS_DEVICE,
        DEFAULT_DEMUCS_MODEL,
        DEFAULT_MP3_BITRATE,
        DEFAULT_OUTPUT_FORMAT,
    )


class SeparateConfig(BaseModel):
    model: str = DEFAULT_DEMUCS_MODEL
    device: Literal["cuda", "cpu"] = DEFAULT_DEMUCS_DEVICE
    output_format: Literal["wav", "mp3"] = DEFAULT_OUTPUT_FORMAT
    mp3_bitrate: int | None = Field(default=None, ge=64, le=320)

    @model_validator(mode="after")
    def validate_mp3_config(self):
        if self.output_format == "mp3" and self.mp3_bitrate is None:
            self.mp3_bitrate = DEFAULT_MP3_BITRATE
        if self.output_format == "wav":
            self.mp3_bitrate = None
        return self


class SeparateMetaResponse(BaseModel):
    job_id: str
    no_vocals_path: str
    vocals_path: str
    model: str
    device: str
    output_format: str
    mp3_bitrate: int | None = None
    duration_ms: int
    status: str
