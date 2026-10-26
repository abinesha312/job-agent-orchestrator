from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class BoardRef:
    source: str  # greenhouse | lever | ashby
    token: str


@dataclass
class JobPosting:
    company: str
    title: str
    source: str
    url: str
    jd_text: str
    posted_at: datetime | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class StoredJob:
    job_id: uuid.UUID
    company: str
    title: str
    source: str
    url: str
    jd_text: str
    posted_at: datetime | None
    metadata: dict
    created_at: datetime
    jd_embedding: list[float] | None = None


@dataclass
class StoredMatch:
    id: uuid.UUID
    job_id: uuid.UUID
    resume_version: uuid.UUID
    match_score: float
    missing_skills: list[str]
    metadata: dict
    created_at: datetime


@dataclass
class StoredApplication:
    id: uuid.UUID
    job_id: uuid.UUID
    status: object
    approved_by_user: bool
    applied_at: datetime | None
    metadata: dict
    created_at: datetime


@dataclass
class StoredContact:
    id: uuid.UUID
    job_id: uuid.UUID
    name: str
    title: str | None
    email: str | None
    source: str
    verified: bool
    confidence: float
    metadata: dict
    created_at: datetime


@dataclass
class RunEvent:
    id: uuid.UUID
    job_id: uuid.UUID | None
    resume_id: uuid.UUID | None
    step: str
    ok: bool
    message: str
    detail: dict
    created_at: datetime
