"""Embed the JD, pull the nearest resume chunks, write a match row."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from job_agent.checks import extract_must_have, keyword_coverage
from job_agent.embeddings.util import embed_texts
from job_agent.errors import NotFound
from job_agent.storage.repository import StoredChunk

# small nudge so a skills blurb beats a header with the same couple of words
_BOOST = {"skills": 0.02, "experience": 0.015, "projects": 0.005, "summary": 0.005, "header": -0.02}

_STOP = {
    "the", "and", "with", "for", "from", "that", "this", "your", "you", "our", "are", "was",
    "have", "has", "will", "into", "about", "role", "job", "team", "work", "using", "their",
}


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    section: str
    text: str
    score: float


@dataclass
class MatchResult:
    chunks: list[RetrievedChunk]
    match_score: float
    missing_skills: list[str]
    resume_version_id: uuid.UUID


def _tokens(text: str) -> set[str]:
    import re
    return {
        t for t in re.findall(r"[a-z0-9+#.]+", (text or "").lower())
        if len(t) > 2 and t not in _STOP
    }


def lexical(chunk: str, jd: str) -> float:
    jt = _tokens(jd)
    if not jt:
        return 0.0
    return len(_tokens(chunk) & jt) / len(jt)


def rank_scored(scored: list[tuple[StoredChunk, float]], jd_text: str, k: int = 5):
    """scored is (chunk, cosine). mix in word overlap, drop the stuff that's way below the best."""
    ranked = []
    for chunk, cos in scored:
        base = 0.75 * max(cos, 0.0) + 0.25 * lexical(chunk.text, jd_text) + _BOOST.get(chunk.section, 0.0)
        ranked.append((chunk, base))
    ranked.sort(key=lambda item: item[1], reverse=True)
    if not ranked:
        return []
    best = ranked[0][1]
    floor = max(0.08, best * 0.45)
    kept = [item for item in ranked if item[1] >= floor]
    return (kept or ranked[:1])[:k]


def _missing(terms: list[str], resume_text: str) -> list[str]:
    return [t for t in terms if keyword_coverage([t], resume_text) < 1.0]


def score_chunks(chunks: list[StoredChunk], query: list[float], jd_text: str, *, k: int = 5) -> list[RetrievedChunk]:
    scored = []
    for chunk in chunks:
        if not chunk.embedding or not query:
            cos = 0.0
        else:
            from job_agent.embeddings.util import cosine
            cos = cosine(chunk.embedding, query)
        scored.append((chunk, cos))
    picked = rank_scored(scored, jd_text, k=k)
    return [
        RetrievedChunk(chunk.id, chunk.section, chunk.text, float(score))
        for chunk, score in picked
    ]


def retrieve_chunks_for_job(job_id: uuid.UUID, resume_id: uuid.UUID, *, store, resumes, embedder,
                            version: int | None = None, k: int = 5) -> list[RetrievedChunk]:
    result = score_match(job_id, None, store=store, resumes=resumes, embedder=embedder,
                         version=version, k=k, resume_id=resume_id, persist=False)
    return result.chunks


def score_match(job_id: uuid.UUID, resume_version_id: uuid.UUID | None = None, *, store, resumes,
                embedder, version: int | None = None, k: int = 5, resume_id: uuid.UUID | None = None,
                persist: bool = True) -> MatchResult:
    job = store.get_job(job_id)
    if job is None:
        raise NotFound(f"unknown job {job_id}")

    if resume_version_id is not None:
        source = resumes.get_version(resume_version_id)
        if source is None:
            raise NotFound(f"unknown resume version {resume_version_id}")
    else:
        source = _source_version(resumes, resume_id)
    ver = version if version is not None else source.version

    query = job.jd_embedding
    if not query:
        query = embed_texts(embedder, [job.jd_text], attempts=2)[0]
        try:
            store.update_job_embedding(job.job_id, query)
        except Exception:
            pass

    # ask for a wider pool; rank_scored cuts it back
    pool = resumes.search_chunks(source.resume_id, ver, query, max(k * 4, 20))
    # search_chunks already returns cosine. rank on that.
    # but the memory path returns StoredChunk with embeddings, sql path may not.
    # lexical re-rank doesn't need the vector again.
    picked = rank_scored(pool, job.jd_text, k=k)
    retrieved = [
        RetrievedChunk(chunk.id, chunk.section, chunk.text, float(score))
        for chunk, score in picked
    ]
    full = resumes.get_chunks(source.resume_id, ver)
    resume_text = "\n".join(c.text for c in full)
    terms = extract_must_have(job.jd_text)
    missing = _missing(terms, resume_text)
    if retrieved:
        match_score = sum(max(0.0, min(1.0, c.score)) for c in retrieved) / len(retrieved)
    else:
        match_score = 0.0
    result = MatchResult(retrieved, match_score, missing, source.version_id)
    if persist:
        store.upsert_match(
            job_id=job.job_id,
            resume_version=source.version_id,
            match_score=match_score,
            missing_skills=missing,
            metadata={
                "chunk_ids": [str(c.chunk_id) for c in retrieved],
                "scores": [round(c.score, 4) for c in retrieved],
                "sections": [c.section for c in retrieved],
            },
        )
    return result


def _source_version(resumes, resume_id: uuid.UUID | None):
    if resume_id is None:
        raise NotFound("resume_id is required")
    versions = resumes.list_versions(resume_id)
    originals = [v for v in versions if (v.metadata or {}).get("kind") != "tailored"]
    if not originals:
        raise NotFound(f"no resume {resume_id}")
    return originals[-1]
