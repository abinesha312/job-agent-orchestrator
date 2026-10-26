from __future__ import annotations

import pytest

from job_agent.agents.resume import parse_and_chunk
from job_agent.parsing import UnsupportedFileType, chunk_resume, detect_sections, extract_text
from job_agent.parsing.extract import ResumeParseError

EXPECTED_SECTIONS = ["header", "summary", "experience", "education", "skills", "projects"]


def test_detect_sections_in_order(resume_text):
    names = [name for name, _ in detect_sections(resume_text)]
    assert names == EXPECTED_SECTIONS


def test_heading_variants_are_recognised():
    text = "Work Experience:\nDid things\nTechnical Skills\nPython\nHonors & Awards\nPrize"
    assert [n for n, _ in detect_sections(text)] == ["experience", "skills", "awards"]


def test_bullet_line_is_not_a_heading():
    text = "SKILLS\n- Education\nPython"
    assert [n for n, _ in detect_sections(text)] == ["skills"]


def test_chunks_have_required_metadata(resume_text):
    chunks = chunk_resume(resume_text, resume_id="r-1", version=2)
    assert chunks
    for i, c in enumerate(chunks):
        assert c.order == i
        assert c.metadata["resume_id"] == "r-1"
        assert c.metadata["version"] == 2
        assert c.metadata["section"] == c.section
        assert c.metadata["order"] == i
        assert c.text.strip()


def test_chunks_never_span_sections_and_respect_max_chars(resume_text):
    chunks = chunk_resume(resume_text, resume_id="r", version=1, max_chars=120)
    assert all(len(c.text) <= 120 for c in chunks)
    exp_text = " ".join(c.text for c in chunks if c.section == "experience")
    assert "FastAPI services" in exp_text and "Prometheus" in exp_text
    edu = [c for c in chunks if c.section == "education"]
    assert all("FastAPI" not in c.text for c in edu)
    # section_order restarts per section
    for sec in {c.section for c in chunks}:
        orders = [c.section_order for c in chunks if c.section == sec]
        assert orders == list(range(len(orders)))


def test_wrapped_bullet_continuation_is_joined():
    text = "EXPERIENCE\n• Built a very long pipeline that\ncontinued on the next line\n• Second"
    chunks = chunk_resume(text, resume_id="r", version=1)
    assert "that continued on the next line" in chunks[0].text


def test_overlong_unit_is_split():
    text = "SUMMARY\n" + " ".join(["word"] * 400)
    chunks = chunk_resume(text, resume_id="r", version=1, max_chars=200)
    assert len(chunks) > 1 and all(len(c.text) <= 200 for c in chunks)


def test_docx_parse_and_chunk(docx_bytes):
    chunks = parse_and_chunk(docx_bytes, "resume.docx", resume_id="r", version=1)
    sections = list(dict.fromkeys(c.section for c in chunks))
    assert sections == EXPECTED_SECTIONS
    assert chunks[0].metadata["file_type"] == "docx"
    assert any("• Built FastAPI" in c.text for c in chunks)


def test_pdf_parse_and_chunk(pdf_bytes):
    text = extract_text(pdf_bytes, "resume.pdf")
    assert "Acme Widgets" in text
    chunks = parse_and_chunk(pdf_bytes, "resume.pdf", resume_id="r", version=1)
    assert list(dict.fromkeys(c.section for c in chunks)) == EXPECTED_SECTIONS
    assert chunks[0].metadata["file_type"] == "pdf"


def test_unsupported_and_bad_files():
    with pytest.raises(UnsupportedFileType):
        extract_text(b"hello", "resume.txt")
    with pytest.raises(ResumeParseError):
        extract_text(b"", "resume.pdf")
    with pytest.raises(ResumeParseError):
        extract_text(b"not a pdf at all", "resume.pdf")
    with pytest.raises(ResumeParseError):
        extract_text(b"not a docx", "resume.docx")
