"""Rewrite one resume for one job. Only facts that are already in the resume."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from job_agent.agents.retrieval import score_match
from job_agent.checks import EvalReport, evaluate, extract_must_have, keyword_coverage
from job_agent.embeddings.util import embed_texts
from job_agent.errors import LlmFailure, NotFound
from job_agent.exporting import write_resume_docx
from job_agent.log import event
from job_agent.parsing.chunker import chunk_resume

_BULLET = re.compile(r"^\s*[•●▪◦‣\-\*–]\s+")
_LLM_CALLS = {"day": "", "n": 0}


@dataclass
class TailorResult:
    version_id: uuid.UUID
    resume_text: str
    email_subject: str
    email_body: str
    docx_path: str
    report: dict
    blocked: bool
    failures: list[str]
    mode: str
    reused: bool = False


def _is_bullet(line: str) -> bool:
    return bool(_BULLET.match(line))


def _hits(text: str, terms: list[str]) -> bool:
    return any(keyword_coverage([t], text) == 1.0 for t in terms)


def _filter_experience(lines: list[str], terms: list[str]) -> list[str]:
    blocks: list[list[str]] = []
    cur: list[str] = []
    for line in lines:
        if line.strip() and not _is_bullet(line) and any(_is_bullet(x) for x in cur):
            blocks.append(cur)
            cur = [line]
        else:
            cur.append(line)
    if cur:
        blocks.append(cur)

    prepared = []
    any_hit = False
    for block in blocks:
        heads = [ln for ln in block if ln.strip() and not _is_bullet(ln)]
        bullets = [ln for ln in block if _is_bullet(ln)]
        hits = [b for b in bullets if _hits(b, terms)]
        if hits:
            any_hit = True
        prepared.append((heads, hits, bullets))

    if not any_hit:
        return lines

    out: list[str] = []
    for heads, hits, _bullets in prepared:
        if not hits:
            continue
        out.extend(heads)
        out.extend(hits)
    return out or lines


def _reorder_skills(lines: list[str], terms: list[str]) -> list[str]:
    out = []
    for line in lines:
        if "," not in line:
            out.append(line)
            continue
        parts = [p.strip() for p in line.split(",") if p.strip()]
        parts.sort(key=lambda p: (0 if _hits(p, terms) else 1, p.lower()))
        out.append(", ".join(parts))
    return out


def text_from_chunks(chunks) -> str:
    """Chunks don't store the heading line, so put it back before we rewrite."""
    parts: list[str] = []
    buf: list[str] = []
    section = None

    def flush() -> None:
        if section is None or not buf:
            return
        body = "\n".join(buf)
        if section == "header":
            parts.append(body)
        else:
            parts.append(section.upper() + "\n" + body)

    for chunk in chunks:
        if section is not None and chunk.section != section:
            flush()
            buf = []
        section = chunk.section
        buf.append(chunk.text)
    flush()
    return "\n\n".join(parts).strip() + ("\n" if parts else "")


def fallback_resume(original: str, terms: list[str]) -> str:
    """Same facts, bullets that match the job floated up. Nothing new."""
    from job_agent.parsing.chunker import detect_sections

    blocks = []
    for name, lines in detect_sections(original):
        body = [ln for ln in lines if ln.strip()]
        if name == "experience":
            filtered = _filter_experience(body, terms)
            if any(_is_bullet(ln) for ln in filtered):
                body = filtered
        elif name == "skills":
            body = _reorder_skills(body, terms)
        if not body:
            continue
        if name == "header":
            blocks.append("\n".join(body))
        else:
            blocks.append(name.upper() + "\n" + "\n".join(body))
    return "\n\n".join(blocks).strip() + "\n"


def _guess_name(original: str) -> str:
    for line in (original or "").splitlines():
        line = line.strip()
        if line and "@" not in line and not line.isupper() and len(line) < 80:
            return line.split("|")[0].strip() or "there"
    return "there"


def fallback_email(name: str, company: str, title: str, resume_text: str) -> tuple[str, str]:
    bullet = ""
    for line in resume_text.splitlines():
        if _is_bullet(line):
            bullet = _BULLET.sub("", line).strip()
            break
    subject = f"{title} — {name}"
    bits = [
        "Hi,",
        "",
        f"I'm {name}. I wanted to reach out about the {title} role at {company}.",
        "",
    ]
    if bullet:
        bits.extend([bullet, ""])
    bits.extend([
        "Happy to share a tailored resume if useful.",
        "",
        "Thanks,",
        name,
        "",
    ])
    return subject, "\n".join(bits)


def _llm_allowed(limit: int) -> bool:
    from datetime import date
    today = date.today().isoformat()
    if _LLM_CALLS["day"] != today:
        _LLM_CALLS["day"] = today
        _LLM_CALLS["n"] = 0
    if _LLM_CALLS["n"] >= limit:
        return False
    _LLM_CALLS["n"] += 1
    return True


def _llm_key() -> str:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""


def _parse_llm_payload(text: str) -> tuple[str, str, str]:
    raw = (text or "").strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise LlmFailure("model did not return json")
    data = json.loads(raw[start:end + 1])
    resume = str(data.get("resume_text") or "").strip()
    subject = str(data.get("email_subject") or "").strip()
    body = str(data.get("email_body") or "").strip()
    if not resume or not subject or not body:
        raise LlmFailure("model json was missing a field")
    return resume, subject, body


def llm_tailor(jd: str, chunks: list[str], original: str, *, model: str) -> tuple[str, str, str]:
    import litellm

    system = (
        "You tailor a resume and a short outreach email. Use ONLY facts from the resume chunks. "
        "Do not add employers, titles, skills, tools, degrees, or numbers that are not in the chunks. "
        "You may drop irrelevant bullets and lightly reorder. Return JSON with keys "
        "resume_text, email_subject, email_body. resume_text should keep plain section headings "
        "like SUMMARY, EXPERIENCE, SKILLS, EDUCATION."
    )
    user = "JOB DESCRIPTION:\n" + jd[:6000] + "\n\nRESUME CHUNKS:\n" + "\n---\n".join(chunks)[:8000]
    resp = litellm.completion(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        timeout=40,
    )
    content = resp.choices[0].message.content or ""
    return _parse_llm_payload(content)


def _existing_tailored(resumes, resume_id, job_id, source_version_id, jd_sha):
    for version in resumes.list_versions(resume_id):
        meta = version.metadata or {}
        if meta.get("kind") != "tailored":
            continue
        if meta.get("job_id") == str(job_id) and meta.get("source_version_id") == str(source_version_id) \
                and meta.get("jd_sha") == jd_sha and meta.get("resume_text"):
            return version
    return None


def tailor_resume(
    resume_version_id: uuid.UUID | None,
    job_id: uuid.UUID,
    *,
    resumes,
    store,
    embedder,
    upload_dir: Path,
    settings=None,
    resume_id: uuid.UUID | None = None,
    k: int = 5,
) -> TailorResult:
    from job_agent.agents.retrieval import _source_version

    job = store.get_job(job_id)
    if job is None:
        raise NotFound(f"unknown job {job_id}")
    if resume_version_id is None:
        source = _source_version(resumes, resume_id)
    else:
        source = resumes.get_version(resume_version_id)
        if source is None:
            raise NotFound(f"unknown resume version {resume_version_id}")

    original_chunks = resumes.get_chunks(source.resume_id, source.version)
    original = text_from_chunks(original_chunks)
    terms = extract_must_have(job.jd_text)
    jd_sha = hashlib.sha256(job.jd_text.encode()).hexdigest()[:16]

    prior = _existing_tailored(resumes, source.resume_id, job.job_id, source.version_id, jd_sha)
    if prior and (prior.metadata or {}).get("resume_text"):
        meta = prior.metadata
        report = meta.get("eval") or {}
        return TailorResult(
            prior.version_id,
            meta.get("resume_text") or "",
            meta.get("email_subject") or "",
            meta.get("email_body") or "",
            meta.get("docx_path") or "",
            report if isinstance(report, dict) else {},
            bool(meta.get("eval_blocked")),
            list((report or {}).get("failures") or []) if isinstance(report, dict) else [],
            meta.get("tailor_mode") or "fallback",
            reused=True,
        )

    match = score_match(
        job.job_id, source.version_id, store=store, resumes=resumes, embedder=embedder, k=k,
    )
    retrieved_text = [c.text for c in match.chunks] or [original]
    mode = "fallback"
    limit = getattr(settings, "daily_llm_calls", 40)
    model = getattr(settings, "llm_model", None) or os.environ.get("LLM_MODEL") or "gemini/gemini-2.5-flash"
    if _llm_key() and _llm_allowed(limit):
        try:
            resume_text, subject, body = llm_tailor(job.jd_text, retrieved_text, original, model=model)
            mode = "llm"
        except Exception as exc:
            event("tailor_llm", ok=False, job_id=str(job.job_id), error=str(exc)[:300])
            resume_text = fallback_resume(original, terms)
            subject, body = fallback_email(_guess_name(original), job.company, job.title, resume_text)
            mode = "fallback"
    else:
        resume_text = fallback_resume(original, terms)
        subject, body = fallback_email(_guess_name(original), job.company, job.title, resume_text)

    # write the docx first so the format gate can open it
    version_num = resumes.next_version(source.resume_id)
    safe_job = str(job.job_id)[:8]
    docx_path = Path(upload_dir) / str(source.resume_id) / f"v{version_num}_{safe_job}_tailored.docx"
    try:
        write_resume_docx(resume_text, docx_path)
    except Exception as exc:
        event("tailor_docx", ok=False, error=str(exc)[:200])
        docx_path = Path("")

    report: EvalReport = evaluate(
        original=original,
        tailored=resume_text,
        jd=job.jd_text,
        retrieved_chunks=retrieved_text,
        must_have=terms,
        docx_path=str(docx_path) if str(docx_path) else None,
        version_count=1,
        llm_model=model,
    )
    new_chunks = chunk_resume(
        resume_text, resume_id=str(source.resume_id), version=version_num,
        extra_metadata={"kind": "tailored", "job_id": str(job.job_id)},
    )
    if not new_chunks:
        # still store something so the version exists
        from job_agent.parsing.chunker import Chunk
        new_chunks = [Chunk(resume_text or " ", "summary", 0, 0, {"kind": "tailored"})]
    embeddings = embed_texts(embedder, [c.text for c in new_chunks])
    meta = {
        "kind": "tailored",
        "job_id": str(job.job_id),
        "source_version_id": str(source.version_id),
        "jd_sha": jd_sha,
        "resume_text": resume_text,
        "email_subject": subject,
        "email_body": body,
        "docx_path": str(docx_path),
        "eval": report.as_dict(),
        "eval_blocked": report.blocked,
        "tailor_mode": mode,
        "embedding_model": getattr(embedder, "name", ""),
    }
    stored = resumes.save_version(
        resume_id=source.resume_id,
        version=version_num,
        file_path=str(docx_path),
        metadata=meta,
        chunks=new_chunks,
        embeddings=embeddings,
        parent_id=source.version_id,
        job_id=job.job_id,
    )
    if report.blocked:
        event("tailor_blocked", ok=False, job_id=str(job.job_id), failures=",".join(report.failures))
    return TailorResult(
        stored.version_id, resume_text, subject, body, str(docx_path),
        report.as_dict(), report.blocked, list(report.failures), mode,
    )
