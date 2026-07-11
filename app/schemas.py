from typing import Literal

from pydantic import BaseModel, Field


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1)
    source: str = Field(default="", max_length=80)


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    content: str | None = Field(default=None, min_length=1)
    source: str | None = Field(default=None, max_length=80)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=10)


class WeeklyReviewRequest(BaseModel):
    week_start: str | None = None
    week_end: str | None = None


class GradeRequest(BaseModel):
    grade: str = Field(min_length=1, max_length=10)


class SettingsUpdate(BaseModel):
    ollama_model: str = Field(min_length=1, max_length=120)


class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    code: str = Field(default="", max_length=40)
    term: str = Field(default="", max_length=80)


class CourseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    code: str | None = Field(default=None, max_length=40)
    term: str | None = Field(default=None, max_length=80)
    status: Literal["active", "archived"] | None = None
