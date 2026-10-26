"""Run the offline gates on the synthetic pairs. No network, no database."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from job_agent.agents.retrieval import rank_scored
from job_agent.agents.tailoring import fallback_email, fallback_resume
from job_agent.checks import evaluate, extract_must_have
from job_agent.embeddings.fake import FakeEmbedder
from job_agent.embeddings.util import cosine
from job_agent.exporting import write_resume_docx
from job_agent.parsing.chunker import chunk_resume
from job_agent.storage.repository import StoredChunk


def dataset_path() -> Path:
    override = os.environ.get("EVAL_DATASET")
    if override:
        return Path(override)
    here = Path(__file__).resolve()
    candidate = here.parents[2] / "evals" / "datasets" / "pairs.jsonl"
    if candidate.exists():
        return candidate
    return Path("evals/datasets/pairs.jsonl")


def load_pairs(path: Path | None = None) -> list[dict]:
    path = path or dataset_path()
    pairs = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            pairs.append(json.loads(line))
    return pairs


def prepare_pair(pair: dict, embedder: FakeEmbedder | None = None) -> dict:
    """Run retrieval and the offline tailoring for one pair and keep the intermediates."""
    embedder = embedder or FakeEmbedder(dim=768)
    text = pair["resume_text"]
    jd = pair["jd_text"]
    terms = list(pair.get("must_have") or extract_must_have(jd))
    chunks = chunk_resume(text, resume_id=str(pair.get("id") or "pair"), version=1)
    vectors = embedder.embed([c.text for c in chunks])
    rid = uuid.uuid4()
    stored = [
        StoredChunk(uuid.uuid4(), rid, 1, c.section, c.order, c.text, {}, datetime.now(UTC), vec)
        for c, vec in zip(chunks, vectors, strict=True)
    ]
    query = embedder.embed([jd])[0]
    scored = [(chunk, cosine(chunk.embedding, query)) for chunk in stored]
    picked = rank_scored(scored, jd, k=5)
    retrieved = [chunk.text for chunk, _score in picked]
    tailored = fallback_resume(text, terms)
    name = pair.get("name") or "Jordan Q. Sample"
    subject, body = fallback_email(name, pair.get("company") or "Example Corp", pair.get("title") or "Engineer", tailored)
    return {
        "id": pair.get("id"), "original": text, "jd": jd, "terms": terms,
        "retrieved": retrieved, "tailored": tailored, "subject": subject, "body": body,
    }


def run_pair(pair: dict, embedder: FakeEmbedder | None = None) -> dict:
    prep = prepare_pair(pair, embedder)
    with tempfile.TemporaryDirectory() as tmp:
        docx_path = Path(tmp) / "tailored.docx"
        write_resume_docx(prep["tailored"], docx_path)
        report = evaluate(
            original=prep["original"],
            tailored=prep["tailored"],
            jd=prep["jd"],
            retrieved_chunks=prep["retrieved"],
            must_have=prep["terms"],
            docx_path=str(docx_path),
        )
    return {
        "id": prep["id"],
        "passed": report.passed,
        "failures": report.failures,
        "scores": {row.name: row.score for row in report.results},
        "subject": prep["subject"],
        "email_ok": bool(prep["body"].strip()),
    }


def run_dataset(path: Path | None = None) -> list[dict]:
    return [run_pair(pair) for pair in load_pairs(path)]
