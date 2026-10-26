"""Offline eval gates. Same thresholds as the plan. DeepEval is optional on top."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from job_agent.log import event

# words that show up in almost every sentence and tell us nothing
_STOP = {
    "a", "an", "the", "and", "or", "of", "to", "for", "in", "on", "with", "at", "from", "by",
    "as", "is", "are", "was", "were", "be", "been", "being", "this", "that", "those", "these",
    "it", "its", "we", "our", "you", "your", "they", "their", "i", "my", "me", "not", "no",
    "into", "over", "under", "about", "than", "then", "so", "if", "but", "per", "via", "using",
    "use", "used", "have", "has", "had", "will", "can", "just", "also", "such",
}

# detectors, not a vocab we're allowed to invent. if one of these shows up in the
# tailored resume and not the original, faithfulness fails.
TECH = {
    "python", "fastapi", "django", "flask", "postgresql", "postgres", "pgvector", "docker",
    "kubernetes", "k8s", "airflow", "gcp", "aws", "azure", "terraform", "prometheus", "grafana",
    "react", "java", "golang", "kafka", "redis", "spark", "pytorch", "tensorflow", "pandas",
    "numpy", "linux", "grpc", "graphql", "javascript", "typescript", "nodejs", "rust", "scala",
    "kotlin", "swift", "ruby", "rails", "php", "mongodb", "elasticsearch", "snowflake",
    "bigquery", "dbt", "sklearn", "mlflow", "langchain", "langfuse", "celery", "rabbitmq",
    "dynamodb", "ansible", "helm", "nginx", "hadoop", "flink", "airbyte", "pydantic",
    "sqlalchemy", "streamlit", "pytest", "cobol", "fortran", "haskell", "elixir", "salesforce", "tableau", "looker", "sagemaker", "vertex", "openai", "gemini", "llm",
    "rag", "microservices", "ci/cd",
}

_EMPLOYER_RE = re.compile(
    r"([A-Z][A-Za-z0-9&.'\-]+(?:\s+[A-Z][A-Za-z0-9&.'\-]+){0,5}\s(?:Inc\.?|LLC|Corp\.?|University|Labs|GmbH))"
)
_TITLE_RE = re.compile(
    r"\b((?:Senior|Staff|Junior|Lead|Principal|Associate)?\s*"
    r"(?:Software|Backend|Frontend|Data|Platform|DevOps|Machine Learning|ML|Full Stack|Full-Stack)\s+"
    r"(?:Engineer|Developer|Scientist))\b",
    re.I,
)
_TOKEN_RE = re.compile(r"[a-z0-9+#.]+")


@dataclass(frozen=True)
class Gate:
    name: str
    checks: str
    threshold: float | None
    kind: str = "min_score"
    hard_fail: bool = False


GATES: list[Gate] = [
    Gate("faithfulness", "No skill/title/employer absent from the original resume", 1.0, hard_fail=True),
    Gate("answer_relevancy", "Tailored resume addresses the JD's required skills", 0.8),
    Gate("keyword_coverage", "Share of must-have JD keywords present", 0.7),
    Gate("retrieval_precision", "Top retrieved chunks relevant to the JD", 0.8),
    Gate("format_check", "Renders, exactly one version, no broken sections", None, kind="pass_fail"),
]

DATASET_SIZE = 20


def _gate(name: str) -> Gate:
    for g in GATES:
        if g.name == name:
            return g
    raise KeyError(name)


def keyword_coverage(must_have: list[str], resume_text: str) -> float:
    """Fraction of must-have keywords found (case-insensitive, whole-token)."""
    if not must_have:
        return 1.0
    text = (resume_text or "").lower()
    hits = 0
    for kw in must_have:
        if not kw or not str(kw).strip():
            hits += 1
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(str(kw).lower())}(?![a-z0-9])", text):
            hits += 1
    return hits / len(must_have)


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def tech_terms(text: str) -> set[str]:
    low = (text or "").lower()
    return {term for term in TECH if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", low)}


def extract_must_have(jd: str) -> list[str]:
    text = jd or ""
    m = re.search(r"must[\s-]*have\s*[:\-]?\s*(.+)", text, flags=re.I)
    if m:
        window = m.group(1).split("\n")[0]
        window = re.split(
            r"\b(nice[\s-]*to[\s-]*have|preferred|bonus)\b", window, maxsplit=1, flags=re.I,
        )[0]
        parts = re.split(r"[,;]|\band\b", window)
        terms = []
        for part in parts:
            part = re.sub(r"[.]+$", "", part).strip(" -•\t")
            if 1 < len(part) <= 40 and len(part.split()) <= 4:
                terms.append(part)
        if terms:
            return _dedupe(terms)
    return sorted(tech_terms(text))


def _employers(text: str) -> set[str]:
    return {re.sub(r"\s+", " ", m).strip(" ,.").lower() for m in _EMPLOYER_RE.findall(text or "")}


def _titles(text: str) -> set[str]:
    return {re.sub(r"\s+", " ", m).strip().lower() for m in _TITLE_RE.findall(text or "")}


def faithfulness(original: str, tailored: str) -> tuple[float, str]:
    problems: list[str] = []
    extra_tech = sorted(tech_terms(tailored) - tech_terms(original))
    if extra_tech:
        problems.append("skills not in resume: " + ", ".join(extra_tech))
    extra_emp = sorted(_employers(tailored) - _employers(original))
    if extra_emp:
        problems.append("employers not in resume: " + ", ".join(extra_emp))
    orig_low = (original or "").lower()
    extra_titles = []
    for title in sorted(_titles(tailored) - _titles(original)):
        words = [
            w for w in title.split()
            if w not in {"senior", "staff", "junior", "lead", "principal", "associate",
                         "engineer", "developer", "scientist", "software", "backend", "frontend"}
        ]
        # "backend engineer" is fine if both words already appear; a new company-ish word is not
        if words and not all(w in orig_low for w in words):
            extra_titles.append(title)
        elif not words and title not in orig_low:
            extra_titles.append(title)
    if extra_titles:
        problems.append("titles not in resume: " + ", ".join(extra_titles))

    orig_words = set(_TOKEN_RE.findall(orig_low))
    for line in (tailored or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith(("•", "-", "*")):
            continue
        words = [w for w in _TOKEN_RE.findall(stripped.lower()) if len(w) > 3 and w not in _STOP]
        if len(words) < 4:
            continue
        hit = sum(1 for w in words if w in orig_words)
        if hit / len(words) < 0.5:
            problems.append("ungrounded bullet: " + stripped[:90])
            break
    return (1.0 if not problems else 0.0), "; ".join(problems)


def answer_relevancy(resume_text: str, terms: list[str]) -> float:
    if not terms:
        return 1.0
    bullets = [ln.strip() for ln in (resume_text or "").splitlines() if ln.strip().startswith(("•", "-", "*"))]
    if not bullets:
        return keyword_coverage(terms, resume_text)
    hits = sum(1 for b in bullets if any(keyword_coverage([t], b) == 1.0 for t in terms))
    return hits / len(bullets)


def retrieval_precision(chunks: list[str], terms: list[str]) -> float:
    if not chunks:
        return 0.0
    if not terms:
        return 1.0
    good = sum(1 for chunk in chunks if any(keyword_coverage([t], chunk) == 1.0 for t in terms))
    return good / len(chunks)


def format_ok(resume_text: str, *, docx_path: str | None = None, version_count: int = 1) -> tuple[bool, str]:
    if version_count != 1:
        return False, f"expected one version, got {version_count}"
    text = (resume_text or "").strip()
    if len(text) < 40:
        return False, "resume text is basically empty"
    low = text.lower()
    if "lorem ipsum" in low or "[insert" in low or "todo:" in low:
        return False, "placeholder text left in the resume"
    heads = sum(1 for h in ("summary", "experience", "skills", "education") if h in low)
    if heads < 2:
        return False, "missing the usual sections"
    if docx_path:
        try:
            import docx

            document = docx.Document(docx_path)
        except Exception as exc:
            return False, f"docx would not open: {exc}"
        if not any(p.text.strip() for p in document.paragraphs):
            return False, "docx has no text"
    return True, ""


@dataclass
class GateScore:
    name: str
    score: float
    passed: bool
    detail: str = ""


@dataclass
class EvalReport:
    passed: bool
    blocked: bool
    failures: list[str]
    results: list[GateScore] = field(default_factory=list)
    judge: dict | None = None

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "blocked": self.blocked,
            "failures": list(self.failures),
            "scores": {r.name: {"score": r.score, "passed": r.passed, "detail": r.detail} for r in self.results},
            "judge": self.judge,
        }


def _judge_enabled() -> bool:
    raw = (os.environ.get("LLM_JUDGE") or "auto").strip().lower()
    if raw in {"0", "off", "false", "no"}:
        return False
    if raw in {"1", "on", "true", "yes"}:
        return True
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY"))


def maybe_llm_judge(*, jd: str, tailored: str, original: str, chunks: list[str], model: str) -> dict | None:
    """DeepEval when a key is present. Any hiccup and we just skip it."""
    if not _judge_enabled():
        return None
    try:
        from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
        from deepeval.test_case import LLMTestCase
    except ImportError:
        return None
    try:
        case = LLMTestCase(
            input=jd[:4000],
            actual_output=tailored[:6000],
            retrieval_context=[c[:1500] for c in chunks[:5]] or [original[:1500]],
            context=[original[:6000]],
        )
        faith = FaithfulnessMetric(threshold=1.0, model=model, async_mode=False, include_reason=False)
        rel = AnswerRelevancyMetric(threshold=0.8, model=model, async_mode=False, include_reason=False)
        faith.measure(case)
        rel.measure(case)
        return {
            "faithfulness": float(faith.score or 0.0),
            "answer_relevancy": float(rel.score or 0.0),
        }
    except Exception as exc:
        event("deepeval", ok=False, error=str(exc)[:300])
        return None


def evaluate(
    *,
    original: str,
    tailored: str,
    jd: str,
    retrieved_chunks: list[str],
    must_have: list[str] | None = None,
    docx_path: str | None = None,
    version_count: int = 1,
    llm_model: str = "",
) -> EvalReport:
    terms = list(must_have) if must_have is not None else extract_must_have(jd)
    results: list[GateScore] = []

    faith, faith_detail = faithfulness(original, tailored)
    faith_gate = _gate("faithfulness")
    results.append(GateScore("faithfulness", faith, faith >= (faith_gate.threshold or 1.0), faith_detail))

    rel = answer_relevancy(tailored, terms)
    rel_gate = _gate("answer_relevancy")
    results.append(GateScore("answer_relevancy", rel, rel >= (rel_gate.threshold or 0.8)))

    cov = keyword_coverage(terms, tailored)
    cov_gate = _gate("keyword_coverage")
    results.append(GateScore("keyword_coverage", cov, cov >= (cov_gate.threshold or 0.7)))

    prec = retrieval_precision(retrieved_chunks, terms)
    prec_gate = _gate("retrieval_precision")
    detail = f"{prec:.2f} on {len(retrieved_chunks)} chunks"
    results.append(GateScore("retrieval_precision", prec, prec >= (prec_gate.threshold or 0.8), detail))

    ok, fmt_detail = format_ok(tailored, docx_path=docx_path, version_count=version_count)
    results.append(GateScore("format_check", 1.0 if ok else 0.0, ok, fmt_detail))

    judge = maybe_llm_judge(
        jd=jd, tailored=tailored, original=original, chunks=retrieved_chunks,
        model=llm_model or os.environ.get("LLM_MODEL") or "gemini/gemini-2.5-flash",
    )
    failures = [r.name for r in results if not r.passed]
    if judge:
        if judge.get("faithfulness", 1.0) < 1.0:
            failures.append("faithfulness_judge")
        if judge.get("answer_relevancy", 1.0) < 0.8:
            failures.append("answer_relevancy_judge")
    blocked = bool(failures)
    return EvalReport(not blocked, blocked, failures, results, judge)
