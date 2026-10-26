"""ApplyPilot UI. Talks to the API, doesn't touch the database itself.

streamlit run ui/streamlit_app.py
"""

from __future__ import annotations

import os

import httpx
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")

st.set_page_config(page_title="ApplyPilot", layout="wide")
st.title("ApplyPilot")
st.caption(
    "Upload a resume, pull jobs, read the draft. "
    "Approving does not apply anywhere and it does not send the email. "
    "I mark a job applied after I submit it myself."
)


def _api(method: str, path: str, **kwargs):
    try:
        resp = httpx.request(method, f"{API_URL}{path}", timeout=60, **kwargs)
    except httpx.HTTPError as exc:
        st.error(f"API is not reachable at {API_URL}: {exc}")
        return None
    if resp.status_code >= 400:
        st.error(f"{resp.status_code}: {resp.text}")
        return None
    if resp.headers.get("content-type", "").startswith("application/json"):
        return resp.json()
    return resp


resume_tab, jobs_tab, review_tab = st.tabs(["Resume", "Jobs", "Review"])

with resume_tab:
    st.subheader("Resume")
    uploaded = st.file_uploader("PDF or DOCX", type=["pdf", "docx"])
    if uploaded is not None and st.button("Parse resume"):
        resp = _api("POST", "/resumes", files={"file": (uploaded.name, uploaded.getvalue())})
        if resp:
            st.session_state["resume_id"] = resp["resume_id"]
            st.success(f"stored {resp['resume_id']} v{resp['version']} ({resp['chunk_count']} chunks)")
    rid = st.session_state.get("resume_id", "")
    rid = st.text_input("resume id", value=rid)
    if rid:
        st.session_state["resume_id"] = rid
        chunks = _api("GET", f"/resumes/{rid}/chunks")
        if chunks:
            for c in chunks["chunks"]:
                with st.expander(f"#{c['order']}  {c['section']}"):
                    st.text(c["text"])

with jobs_tab:
    st.subheader("Find jobs")
    st.write("Public boards only. One bad board won't wipe the others.")
    gh = st.text_input("Greenhouse board tokens", placeholder="example, another")
    lever = st.text_input("Lever slugs")
    ashby = st.text_input("Ashby boards")
    roles = st.text_input("Only titles or text containing", placeholder="backend, python")
    if st.button("Run discovery"):
        if not st.session_state.get("resume_id"):
            st.warning("Parse a resume first if you want to match right after.")
        body = {
            "greenhouse": [p.strip() for p in gh.split(",") if p.strip()],
            "lever": [p.strip() for p in lever.split(",") if p.strip()],
            "ashby": [p.strip() for p in ashby.split(",") if p.strip()],
            "roles": [p.strip() for p in roles.split(",") if p.strip()],
        }
        found = _api("POST", "/discovery", json=body)
        if found:
            st.write(f"saved {found['saved']} ({found['created']} new)")
            for err in found["errors"]:
                st.warning(err)
    st.divider()
    st.subheader("Or paste one")
    with st.form("paste"):
        company = st.text_input("Company")
        title = st.text_input("Title")
        url = st.text_input("URL")
        jd = st.text_area("Job text")
        if st.form_submit_button("Save job") and company and title and url and jd:
            saved = _api("POST", "/jobs/import", json={
                "company": company, "title": title, "url": url, "jd_text": jd,
            })
            if saved:
                st.success(f"saved {saved['job_id']}")
    if st.button("Run matching and drafts"):
        rid = st.session_state.get("resume_id")
        if not rid:
            st.warning("Need a resume id first.")
        else:
            ran = _api("POST", "/pipeline/run", json={"resume_id": rid})
            if ran:
                for row in ran["results"]:
                    st.write(f"{row['job_id']}  {row['status']}  {', '.join(row['notes'])}")

with review_tab:
    st.subheader("Review")
    apps = _api("GET", "/applications")
    if not apps:
        st.info("Nothing queued yet.")
    else:
        labels = {
            f"{a['company']} — {a['title']} ({a['status']})": a["id"]
            for a in apps["applications"]
        }
        if not labels:
            st.info("Nothing queued yet.")
        else:
            pick = st.selectbox("Application", list(labels))
            app_id = labels[pick]
            draft = _api("GET", f"/applications/{app_id}/draft")
            if draft:
                blocked = draft.get("eval_blocked")
                if blocked:
                    fails = ", ".join((draft.get("eval") or {}).get("failures") or [])
                    st.warning(f"Gates failed ({fails}). It will not go to approval until this is fixed.")
                score = draft.get("match_score")
                if score is not None:
                    st.write(f"match score {score:.2f}")
                missing = draft.get("missing_skills") or []
                if missing:
                    st.write("missing from the resume: " + ", ".join(missing))
                resume_text = st.text_area("Tailored resume", draft["resume_text"], height=280)
                subject = st.text_input("Email subject", draft["email_subject"])
                body = st.text_area("Email draft", draft["email_body"], height=160)
                contacts = draft.get("contacts") or []
                if contacts:
                    st.write("Contacts (none of these are verified, and nothing is emailed):")
                    for c in contacts:
                        st.write(f"- {c['name']}  {c.get('email') or ''}  {c['source']}  confidence {c['confidence']}")
                who = st.text_input("Your name on the approval", value="me")
                c1, c2, c3, c4 = st.columns(4)
                if c1.button("Save edits"):
                    updated = _api("PATCH", f"/applications/{app_id}/draft", json={
                        "resume_text": resume_text, "email_subject": subject, "email_body": body,
                    })
                    if updated:
                        st.success(f"saved, status {updated['status']}")
                if (not blocked) and c2.button("Approve"):
                    approved = _api("POST", f"/applications/{app_id}/approve", json={"approved_by": who or "me"})
                    if approved:
                        st.success(f"approved by you. status {approved['status']}. still not submitted.")
                elif blocked:
                    c2.caption("Fix the draft before approving.")
                if c3.button("Reject"):
                    rejected = _api("POST", f"/applications/{app_id}/reject")
                    if rejected:
                        st.write(f"status {rejected['status']}")
                docx = _api("GET", f"/applications/{app_id}/docx")
                if docx is not None and hasattr(docx, "content"):
                    c4.download_button("Download docx", docx.content, file_name="tailored.docx")
                if st.button("I submitted this myself, mark applied"):
                    marked = _api("POST", f"/applications/{app_id}/applied")
                    if marked:
                        st.success(f"status {marked['status']}")

st.divider()
st.caption("ApplyPilot does not auto-apply and does not send email.")
