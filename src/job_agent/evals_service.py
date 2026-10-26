"""Eval suites behind the Evals tab.

Offline suites compute the RAGAS metric definitions (context precision, context recall,
faithfulness, answer relevancy) deterministically, so they run with no key. The two engine
suites call the real libraries when they are installed and configured:

* ragas      RAGAS with an OpenAI judge
* deepeval   DeepEval faithfulness and answer relevancy with an OpenAI judge

An engine that is not installed or not configured reports ``skipped`` with the reason.
It never fakes a score.
"""

from __future__ import annotations

import importlib.util
import os
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from job_agent.approval.gate import ApprovalRequiredError, approve, transition
from job_agent.checks import (
    _STOP,
    _TOKEN_RE,
    GATES,
    answer_relevancy,
    evaluate,
    faithfulness,
    format_ok,
    keyword_coverage,
)
from job_agent.db.models import ApplicationStatus as S
from job_agent.evalrun import load_pairs, prepare_pair
from job_agent.exporting import write_resume_docx

THRESHOLDS = {
    "context_precision": 0.8,
    "context_recall": 0.7,
    "faithfulness": 1.0,
    "answer_relevancy": 0.8,
    "keyword_coverage": 0.7,
    "format_check": 1.0,
}


def _has(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


SUITES: list[dict] = [
    {"id": "retrieval", "name": "Retrieval quality", "engine": "ragas-metrics (offline)",
     "metrics": ["context_precision", "context_recall"],
     "about": "Are the resume chunks pulled for a job the right ones, and in a useful order?"},
    {"id": "generation", "name": "Generation quality", "engine": "ragas-metrics (offline)",
     "metrics": ["faithfulness", "answer_relevancy", "keyword_coverage"],
     "about": "Is every claim in the tailored resume supported by the original, and does it answer the job?"},
    {"id": "format", "name": "Format and ATS", "engine": "rule-based",
     "metrics": ["format_check"],
     "about": "Does the draft render to a real DOCX, keep its sections, and avoid placeholder text?"},
    {"id": "safety", "name": "Hallucination and approval guardrails", "engine": "adversarial",
     "metrics": ["detection_rate", "guard_rate"],
     "about": "Plant fake skills and employers and confirm the gates catch them. Confirm nothing is approved without the user."},
    {"id": "gates", "name": "Release gates (golden set)", "engine": "rule-based",
     "metrics": ["pass_rate"],
     "about": "All five hard gates over the 20 synthetic resume and job pairs."},
    {"id": "live", "name": "Live applications", "engine": "rule-based",
     "metrics": ["pass_rate"],
     "about": "Re-scores the drafts currently in the pipeline, not the golden set."},
    {"id": "ragas", "name": "RAGAS (LLM judge)", "engine": "ragas",
     "metrics": ["faithfulness", "answer_relevancy", "context_precision", "context_recall"],
     "about": "The real RAGAS library with an LLM judge on a sample of the golden set."},
    {"id": "deepeval", "name": "DeepEval (LLM judge)", "engine": "deepeval",
     "metrics": ["faithfulness", "answer_relevancy"],
     "about": "DeepEval's faithfulness and answer relevancy metrics with an LLM judge on a sample of the golden set."},
]


def catalog() -> dict:
    engines = [
        {"id": "builtin", "name": "Built-in RAGAS-style metrics", "available": True, "reason": ""},
        {"id": "ragas", "name": "ragas",
         "available": _has("ragas") and bool(os.environ.get("OPENAI_API_KEY")),
         "reason": "" if _has("ragas") and os.environ.get("OPENAI_API_KEY")
         else ("pip install ragas" if not _has("ragas") else "set OPENAI_API_KEY")},
        {"id": "deepeval", "name": "deepeval",
         "available": _has("deepeval") and bool(os.environ.get("OPENAI_API_KEY")),
         "reason": "" if _has("deepeval") and os.environ.get("OPENAI_API_KEY")
         else ("pip install deepeval" if not _has("deepeval") else "set OPENAI_API_KEY")},
    ]
    return {"suites": SUITES, "engines": engines, "thresholds": THRESHOLDS,
            "gates": [{"name": g.name, "checks": g.checks, "threshold": g.threshold, "hard_fail": g.hard_fail}
                      for g in GATES]}


# ---- metric definitions -------------------------------------------------

def context_precision(chunks: list[str], terms: list[str]) -> float:
    """Average precision@k over ranked chunks. A chunk is relevant if it holds a must-have term."""
    if not chunks:
        return 0.0
    if not terms:
        return 1.0
    rel = [any(keyword_coverage([t], c) == 1.0 for t in terms) for c in chunks]
    hits, total = 0, 0.0
    for i, r in enumerate(rel, start=1):
        if r:
            hits += 1
            total += hits / i
    return total / hits if hits else 0.0


def context_recall(chunks: list[str], terms: list[str], original: str) -> float:
    """Of the must-have terms the resume can truthfully claim, how many did retrieval surface?"""
    reachable = [t for t in terms if keyword_coverage([t], original) == 1.0]
    if not reachable:
        return 1.0
    joined = "\n".join(chunks)
    return keyword_coverage(reachable, joined)


def claim_faithfulness(original: str, tailored: str) -> float:
    """Share of bullet claims whose content words are mostly present in the original."""
    orig_words = set(_TOKEN_RE.findall((original or "").lower()))
    claims, ok = 0, 0
    for line in (tailored or "").splitlines():
        s = line.strip()
        if not s.startswith(("•", "-", "*")):
            continue
        words = [w for w in _TOKEN_RE.findall(s.lower()) if len(w) > 3 and w not in _STOP]
        if len(words) < 3:
            continue
        claims += 1
        if sum(1 for w in words if w in orig_words) / len(words) >= 0.5:
            ok += 1
    base, _ = faithfulness(original, tailored)
    ratio = ok / claims if claims else 1.0
    return min(ratio, base) if base < 1.0 else ratio


# ---- helpers ------------------------------------------------------------

def _case(cid, scores: dict, notes: str = "", metrics: list[str] | None = None) -> dict:
    checks = {m: scores[m] >= THRESHOLDS[m] for m in scores if m in THRESHOLDS}
    return {"id": cid, "scores": scores, "passed": all(checks.values()) if checks else True,
            "notes": notes, "checks": checks}


def _summary(cases: list[dict]) -> dict:
    keys: list[str] = []
    for c in cases:
        for k in c["scores"]:
            if k not in keys:
                keys.append(k)
    out = {}
    for k in keys:
        vals = [c["scores"][k] for c in cases if k in c["scores"]]
        out[k] = round(sum(vals) / len(vals), 4) if vals else None
    return out


def _result(suite_id: str, cases: list[dict], started: float, *, notes: str = "",
            status: str | None = None, extra: dict | None = None) -> dict:
    meta = next(s for s in SUITES if s["id"] == suite_id)
    passed = sum(1 for c in cases if c["passed"])
    if status is None:
        status = "passed" if cases and passed == len(cases) else ("failed" if cases else "skipped")
    return {
        "id": str(uuid.uuid4()), "suite": suite_id, "name": meta["name"], "engine": meta["engine"],
        "started_at": datetime.now(UTC).isoformat(), "duration_ms": int((time.perf_counter() - started) * 1000),
        "status": status, "total": len(cases), "passed": passed, "failed": len(cases) - passed,
        "summary": _summary(cases), "cases": cases, "notes": notes, **(extra or {}),
    }


def _skipped(suite_id: str, started: float, reason: str) -> dict:
    return _result(suite_id, [], started, notes=reason, status="skipped")


# ---- offline suites -----------------------------------------------------

def _retrieval(pairs: list[dict]) -> list[dict]:
    cases = []
    for pair in pairs:
        p = prepare_pair(pair)
        cp = context_precision(p["retrieved"], p["terms"])
        cr = context_recall(p["retrieved"], p["terms"], p["original"])
        cases.append(_case(p["id"], {"context_precision": round(cp, 4), "context_recall": round(cr, 4)},
                           f"{len(p['retrieved'])} chunks, {len(p['terms'])} must-have terms"))
    return cases


def _generation(pairs: list[dict]) -> list[dict]:
    cases = []
    for pair in pairs:
        p = prepare_pair(pair)
        f, detail = faithfulness(p["original"], p["tailored"])
        cf = claim_faithfulness(p["original"], p["tailored"])
        scores = {
            "faithfulness": round(min(f, cf), 4),
            "answer_relevancy": round(answer_relevancy(p["tailored"], p["terms"]), 4),
            "keyword_coverage": round(keyword_coverage(p["terms"], p["tailored"]), 4),
        }
        cases.append(_case(p["id"], scores, detail))
    return cases


def _format(pairs: list[dict]) -> list[dict]:
    cases = []
    for pair in pairs:
        p = prepare_pair(pair)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.docx"
            write_resume_docx(p["tailored"], path)
            ok, detail = format_ok(p["tailored"], docx_path=str(path))
        cases.append(_case(p["id"], {"format_check": 1.0 if ok else 0.0}, detail))
    return cases


def _gates(pairs: list[dict]) -> list[dict]:
    cases = []
    for pair in pairs:
        p = prepare_pair(pair)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.docx"
            write_resume_docx(p["tailored"], path)
            rep = evaluate(original=p["original"], tailored=p["tailored"], jd=p["jd"],
                           retrieved_chunks=p["retrieved"], must_have=p["terms"], docx_path=str(path))
        scores = {r.name: round(r.score, 4) for r in rep.results}
        cases.append({"id": p["id"], "scores": scores, "passed": rep.passed,
                      "notes": ", ".join(rep.failures), "checks": {r.name: r.passed for r in rep.results}})
    return cases


_FAKE_SKILLS = ["Kubernetes", "Terraform", "Kafka", "Rust", "Snowflake"]


def _safety(pairs: list[dict]) -> list[dict]:
    cases = []
    for pair in pairs:
        p = prepare_pair(pair)
        fake = next((s for s in _FAKE_SKILLS if s.lower() not in p["original"].lower()), "Haskell")
        poisoned = p["tailored"] + f"\n• Led {fake} platform migration for Imaginary Systems Inc.\n"
        f, _ = faithfulness(p["original"], poisoned)
        caught = f < 1.0
        clean_f, _ = faithfulness(p["original"], p["tailored"])
        cases.append(_case(p["id"], {"detection_rate": 1.0 if caught else 0.0,
                                     "false_alarm_free": 1.0 if clean_f == 1.0 else 0.0},
                           f"planted {fake} and a fake employer; caught={caught}"))
        cases[-1]["passed"] = caught and clean_f == 1.0
        cases[-1]["checks"] = {"detection_rate": caught, "false_alarm_free": clean_f == 1.0}
    # approval guardrails run once, not per pair
    guards = []
    v1 = {"status": S.discovered, "approved_by_user": False, "metadata": {}}
    try:
        transition(v1, S.approved)
        refused = False
    except Exception:
        refused = True
    guards.append(("skip_to_approved_refused", refused))
    v2 = {"status": S.awaiting_approval, "approved_by_user": False, "metadata": {}}
    try:
        transition(v2, S.applied)
        refused = False
    except (ApprovalRequiredError, Exception):
        refused = True
    guards.append(("apply_without_approval_refused", refused))
    v3 = {"status": S.awaiting_approval, "approved_by_user": False, "metadata": {}}
    try:
        approve(v3, approved_by="eval")
        ok = v3["approved_by_user"] is True and S(v3["status"]) == S.approved
    except Exception:
        ok = False
    guards.append(("explicit_approve_works", ok))
    for name, ok in guards:
        cases.append({"id": f"guard:{name}", "scores": {"guard_rate": 1.0 if ok else 0.0},
                      "passed": ok, "notes": "", "checks": {"guard_rate": ok}})
    return cases


def _live(store, resumes) -> list[dict]:
    cases = []
    for app in store.list_applications():
        meta = app.metadata or {}
        tailored = meta.get("tailored_resume")
        if not tailored:
            continue
        job = store.get_job(app.job_id)
        original = ""
        raw = meta.get("source_version_id")
        if raw:
            ver = resumes.get_version(uuid.UUID(str(raw)))
            if ver:
                original = "\n".join(c.text for c in resumes.get_chunks(ver.resume_id, ver.version))
        rep = evaluate(original=original or tailored, tailored=tailored, jd=job.jd_text if job else "",
                       retrieved_chunks=list(meta.get("retrieved_chunks") or []))
        scores = {r.name: round(r.score, 4) for r in rep.results}
        label = f"{job.company} - {job.title}" if job else str(app.id)
        cases.append({"id": label, "scores": scores, "passed": rep.passed,
                      "notes": ", ".join(rep.failures), "checks": {r.name: r.passed for r in rep.results}})
    return cases


# ---- engine suites ------------------------------------------------------

def _ragas(pairs: list[dict], sample: int) -> tuple[list[dict], str]:
    if not _has("ragas"):
        return [], "ragas is not installed. pip install ragas"
    if not os.environ.get("OPENAI_API_KEY"):
        return [], "ragas needs a judge model. Set OPENAI_API_KEY."
    try:
        from ragas import EvaluationDataset
        from ragas import evaluate as ragas_eval
        from ragas.embeddings import embedding_factory
        from ragas.llms import llm_factory
        from ragas.metrics import (
            Faithfulness,
            LLMContextPrecisionWithoutReference,
            LLMContextRecall,
            ResponseRelevancy,
        )
    except Exception as exc:
        return [], f"ragas import failed: {exc}"
    rows, ids = [], []
    for pair in pairs[:sample]:
        p = prepare_pair(pair)
        rows.append({
            "user_input": p["jd"], "response": p["tailored"], "retrieved_contexts": p["retrieved"],
            "reference": p["original"],
        })
        ids.append(p["id"])
    try:
        llm = llm_factory(os.environ.get("RAGAS_MODEL", "gpt-4o-mini"))
        emb = embedding_factory()
        res = ragas_eval(EvaluationDataset.from_list(rows), metrics=[
            Faithfulness(), ResponseRelevancy(), LLMContextPrecisionWithoutReference(), LLMContextRecall(),
        ], llm=llm, embeddings=emb)
        df = res.to_pandas()
    except Exception as exc:
        return [], f"ragas run failed: {str(exc)[:300]}"
    cases = []
    colmap = {"faithfulness": "faithfulness", "answer_relevancy": "answer_relevancy",
              "llm_context_precision_without_reference": "context_precision", "context_recall": "context_recall"}
    for cid, (_, row) in zip(ids, df.iterrows(), strict=False):
        scores = {v: round(float(row[k]), 4) for k, v in colmap.items() if k in row and row[k] == row[k]}
        cases.append(_case(cid, scores))
    return cases, ""


def _deepeval(pairs: list[dict], sample: int) -> tuple[list[dict], str]:
    if not _has("deepeval"):
        return [], "deepeval is not installed. pip install deepeval"
    if not os.environ.get("OPENAI_API_KEY"):
        return [], "deepeval needs a judge model. Set OPENAI_API_KEY."
    try:
        from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
        from deepeval.test_case import LLMTestCase
    except Exception as exc:
        return [], f"deepeval import failed: {exc}"
    model = os.environ.get("DEEPEVAL_MODEL", "gpt-4o-mini")
    cases = []
    try:
        for pair in pairs[:sample]:
            p = prepare_pair(pair)
            case = LLMTestCase(
                input=p["jd"][:4000], actual_output=p["tailored"][:6000],
                retrieval_context=[c[:1500] for c in p["retrieved"][:5]] or [p["original"][:1500]],
            )
            faith = FaithfulnessMetric(threshold=1.0, model=model, async_mode=False, include_reason=False)
            rel = AnswerRelevancyMetric(threshold=0.8, model=model, async_mode=False, include_reason=False)
            faith.measure(case)
            rel.measure(case)
            scores = {"faithfulness": round(float(faith.score or 0.0), 4),
                      "answer_relevancy": round(float(rel.score or 0.0), 4)}
            cases.append(_case(p["id"], scores))
    except Exception as exc:
        return [], f"deepeval run failed: {str(exc)[:300]}"
    return cases, ""


# ---- entry point --------------------------------------------------------

def run_suite(suite_id: str, *, store=None, resumes=None, sample: int = 5) -> dict:
    started = time.perf_counter()
    if suite_id not in {s["id"] for s in SUITES}:
        raise KeyError(suite_id)
    if suite_id == "live":
        cases = _live(store, resumes)
        if not cases:
            return _skipped("live", started, "No drafts yet. Run the pipeline first.")
        return _result("live", cases, started)
    pairs = load_pairs()
    if suite_id == "ragas":
        cases, why = _ragas(pairs, sample)
        return _result("ragas", cases, started, notes=why) if cases else _skipped("ragas", started, why)
    if suite_id == "deepeval":
        cases, why = _deepeval(pairs, sample)
        return _result("deepeval", cases, started, notes=why) if cases else _skipped("deepeval", started, why)
    fn = {"retrieval": _retrieval, "generation": _generation, "format": _format,
          "safety": _safety, "gates": _gates}[suite_id]
    return _result(suite_id, fn(pairs), started)
