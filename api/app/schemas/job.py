from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.base import APIModel


class JobCreate(BaseModel):
    mode: Literal["merged", "per_file", "concat"]
    number_of_questions: int = Field(ge=5, le=200)
    difficulty: Literal["easy", "medium", "hard"]
    avoid_repeats: bool = True
    include_answers: bool = True


class JobOut(APIModel):
    id: UUID
    topic_id: UUID
    user_id: int
    mode: str
    status: str
    progress: int
    stage: str
    params_json: dict
    result_paths: dict | None
    metrics_json: dict | None
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None
