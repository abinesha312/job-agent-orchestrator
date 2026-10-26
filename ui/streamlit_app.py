"""Streamlit UI — STUB (Phase 7).

Run: pip install -e '.[ui]' && streamlit run ui/streamlit_app.py
(expects the API at API_URL, default http://localhost:8000)

Working today: upload a resume and view its chunks (calls the Phase 1 API).
TODO(phase-7): job list with match scores, side-by-side diff of tailored vs original
resume, approve/reject buttons (the ONLY place approval should originate), status tracking.
"""

from __future__ import annotations

import os

import httpx
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Job Agent Orchestrator", layout="wide")
st.title("Job Agent Orchestrator")
st.caption("Phase 1: resume upload + chunk viewer. Approval queue arrives in Phase 7.")

uploaded = st.file_uploader("Upload resume (.pdf or .docx)", type=["pdf", "docx"])
if uploaded is not None and st.button("Parse resume"):
    r = httpx.post(f"{API_URL}/resumes", files={"file": (uploaded.name, uploaded.getvalue())}, timeout=60)
    if r.status_code != 201:
        st.error(f"{r.status_code}: {r.text}")
    else:
        body = r.json()
        st.success(f"resume_id {body['resume_id']} v{body['version']}: {body['chunk_count']} chunks")
        chunks = httpx.get(f"{API_URL}/resumes/{body['resume_id']}/chunks", timeout=30).json()["chunks"]
        for c in chunks:
            with st.expander(f"#{c['order']} · {c['section']}"):
                st.text(c["text"])

st.divider()
st.subheader("Approval queue")
st.info("TODO(phase-7): not implemented. Nothing is ever submitted or emailed without your approval.")
