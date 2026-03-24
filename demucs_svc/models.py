from pydantic import BaseModel


class SeparateMetaResponse(BaseModel):
    job_id: str
    no_vocals_path: str
    vocals_path: str
    model: str
    duration_ms: int
    status: str
