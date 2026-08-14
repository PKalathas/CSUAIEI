"""
Curriculum Designer — Demo Frontend
Run: streamlit run frontend/app.py
Requires the FastAPI backend running on http://localhost:8003
"""

import json

import requests
import streamlit as st

API_URL = "http://localhost:8003"

st.set_page_config(
    page_title="Curriculum Designer",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("Curriculum Designer")

# ── API health ────────────────────────────────────────────────────────────────

try:
    health = requests.get(f"{API_URL}/health", timeout=3)
    if health.status_code == 200:
        st.success("API connected · http://localhost:8003")
    else:
        st.error(f"API returned {health.status_code}")
except Exception:
    st.error("Cannot reach API at http://localhost:8003 — start the backend first.")


# ── Helpers ───────────────────────────────────────────────────────────────────

STATUS_COLOR = {
    "pending": "orange",
    "approved": "green",
    "needs_changes": "red",
}

DIFFICULTY_LABEL = {
    "basic": "[basic]",
    "intermediate": "[mid]",
    "challenge": "[hard]",
}


def _display_lab(lab: dict) -> None:
    col_meta1, col_meta2, col_meta3 = st.columns(3)
    status = lab.get("approval_status", "pending")
    col_meta1.metric("Version", f"v{lab.get('version', 1)}")
    col_meta2.metric("Status", status.upper())
    col_meta3.metric("Questions", len(lab.get("quiz", [])))

    if lab.get("material_content"):
        doc_count = lab["material_content"].count("[Document ")
        st.info(
            f"PDF context loaded ({doc_count} document(s)) — "
            f"{len(lab['material_content']):,} chars injected into prompts"
        )

    spec_tab, quiz_tab, rubric_tab = st.tabs(["Spec", "Quiz", "Rubric"])

    with spec_tab:
        st.markdown(lab.get("spec_markdown", "_No spec generated yet._"))

    with quiz_tab:
        quiz = lab.get("quiz", [])
        if not quiz:
            st.info("No quiz generated yet.")
        for q in quiz:
            diff_label = DIFFICULTY_LABEL.get(q.get("difficulty", ""), "")
            label = f"{diff_label} **{q['id']}** · {q.get('difficulty','?')} · {q.get('type','?')} · {q.get('rubric_points', 0)} pts"
            with st.expander(label):
                st.markdown(f"**Question:** {q['question']}")
                st.markdown(f"**Expected answer:** {q['expected_answer']}")
                if q.get("learning_objective_ref"):
                    st.caption(f"Objective: {q['learning_objective_ref']}")

    with rubric_tab:
        rubric = lab.get("rubric", {})
        c1, c2, c3 = st.columns(3)
        c1.metric("Code", f"{rubric.get('code_weight', 0)*100:.0f}%")
        c2.metric("Report", f"{rubric.get('report_weight', 0)*100:.0f}%")
        c3.metric("Manual", f"{rubric.get('manual_weight', 0)*100:.0f}%")
        criteria = rubric.get("criteria", [])
        if criteria:
            st.markdown("**Criteria**")
            for c in criteria:
                st.markdown(
                    f"- **{c['name']}** ({c['weight']*100:.0f}%): {c['description']}"
                )


def _get_pdf_export(lab_id: str, kind: str) -> tuple[bytes | None, str | None]:
    try:
        response = requests.get(f"{API_URL}/curriculum/{lab_id}/export/{kind}.pdf", timeout=20)
        if not response.ok:
            return None, f"Export failed ({response.status_code})"
        return response.content, None
    except Exception as exc:
        return None, str(exc)


# ── Layout ────────────────────────────────────────────────────────────────────

left, right = st.columns([1, 2], gap="large")

# ── Left panel: controls ──────────────────────────────────────────────────────

with left:
    st.subheader("Generate Lab")

    with st.form("generate_form"):
        lab_id = st.text_input("Lab ID", "lab_001")
        instructor_id = st.text_input("Instructor ID", "prof_demo")
        title = st.text_input("Lab Title", "Introduction to Linked Lists")
        objectives_raw = st.text_area(
            "Learning Objectives (one per line)",
            "Implement a singly linked list in Python\n"
            "Understand time complexity of insert and delete",
            height=100,
        )
        difficulty = st.selectbox(
            "Difficulty", ["beginner", "intermediate", "advanced"], index=1
        )
        duration = st.number_input("Duration (minutes)", value=90, step=15)
        pdfs = st.file_uploader(
            "Reference Material PDFs (optional)",
            type=["pdf"],
            accept_multiple_files=True,
            help="Upload one or more PDFs — extracted text is injected into every LLM prompt.",
        )
        submitted = st.form_submit_button("Generate Lab", type="primary", use_container_width=True)

    if submitted:
        objectives = [o.strip() for o in objectives_raw.strip().splitlines() if o.strip()]
        form_data = {
            "lab_id": lab_id,
            "instructor_id": instructor_id,
            "title": title,
            "learning_objectives": json.dumps(objectives),
            "difficulty": difficulty,
            "estimated_duration_min": str(duration),
        }
        files = [
            ("files", (pdf.name, pdf.getvalue(), "application/pdf"))
            for pdf in (pdfs or [])
        ]

        with st.spinner("Generating… (30–60 s with Azure LLM, ~1 s in mock mode)"):
            try:
                resp = requests.post(
                    f"{API_URL}/curriculum/generate-with-material",
                    data=form_data,
                    files=files if files else None,
                    timeout=120,
                )
                if resp.status_code == 200:
                    st.session_state["lab"] = resp.json()
                    st.session_state.pop("typo_result", None)
                    st.success("Lab generated!")
                else:
                    try:
                        detail = resp.json()
                    except Exception:
                        detail = resp.text
                    st.error(f"Error {resp.status_code}: {detail}")
            except Exception as exc:
                st.error(str(exc))

    # ── Manage existing lab ───────────────────────────────────────────────────

    st.divider()
    st.subheader("Manage Lab")

    load_id = st.text_input("Load by Lab ID", placeholder="lab_001")
    if st.button("Load", use_container_width=True):
        try:
            r = requests.get(f"{API_URL}/curriculum/{load_id}", timeout=10)
            if r.status_code == 200:
                st.session_state["lab"] = r.json()
                st.session_state.pop("typo_result", None)
            else:
                st.error(f"Not found ({r.status_code})")
        except Exception as exc:
            st.error(str(exc))

    if "lab" in st.session_state:
        lab = st.session_state["lab"]
        current_lab_id = lab["lab_id"]
        status = lab.get("approval_status", "pending")

        st.caption(f"Current: **{current_lab_id}** · status: **{status}**")

        st.markdown("**Actions**")
        col_a, col_b = st.columns(2)

        with col_a:
            if st.button("Approve", use_container_width=True, disabled=(status == "approved")):
                r = requests.post(
                    f"{API_URL}/curriculum/{current_lab_id}/approve",
                    json={"approved_by": instructor_id, "notes": ""},
                    timeout=10,
                )
                if r.ok:
                    st.session_state["lab"] = r.json()
                    st.rerun()
                else:
                    st.error(r.text)

        with col_b:
            if st.button("Check Typos", use_container_width=True):
                with st.spinner("Proofreading…"):
                    r = requests.post(
                        f"{API_URL}/curriculum/{current_lab_id}/check-typos",
                        timeout=60,
                    )
                    if r.ok:
                        st.session_state["typo_result"] = r.json()
                    else:
                        st.error(r.text)

        if "typo_result" in st.session_state:
            typo = st.session_state["typo_result"]
            if typo["issues_found"] == 0:
                st.success("No issues found.")
            else:
                st.warning(f"{typo['issues_found']} issue(s) found:")
                for issue in typo["issues"]:
                    st.markdown(
                        f"- **{issue['location']}** `{issue['type']}`: {issue['suggestion']}"
                    )

        with st.form("changes_form"):
            feedback = st.text_area(
                "Request Changes",
                placeholder="e.g. Add more challenge-level questions and clarify rubric criterion 2.",
                height=80,
            )
            change_submitted = st.form_submit_button(
                "Request Changes & Regenerate", use_container_width=True
            )

        if change_submitted and feedback.strip():
            with st.spinner("Regenerating quiz + rubric…"):
                r = requests.post(
                    f"{API_URL}/curriculum/{current_lab_id}/request-changes",
                    json={"feedback": feedback, "requested_by": instructor_id},
                    timeout=120,
                )
                if r.ok:
                    st.session_state["lab"] = r.json()
                    st.session_state.pop("typo_result", None)
                    st.rerun()
                else:
                    st.error(r.text)

# ── Right panel: results ──────────────────────────────────────────────────────

with right:
    if "lab" in st.session_state:
        lab = st.session_state["lab"]
        st.subheader(f"{lab['title']}")
        export_col1, export_col2, export_col3 = st.columns(3)

        with export_col1:
            lab_pdf, lab_pdf_err = _get_pdf_export(lab["lab_id"], "lab")
            if lab_pdf:
                st.download_button(
                    "Download Lab PDF",
                    data=lab_pdf,
                    file_name=f"{lab['lab_id']}_lab.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            elif lab_pdf_err:
                st.caption(lab_pdf_err)

        with export_col2:
            quiz_pdf, quiz_pdf_err = _get_pdf_export(lab["lab_id"], "quiz")
            if quiz_pdf:
                st.download_button(
                    "Download Quiz PDF",
                    data=quiz_pdf,
                    file_name=f"{lab['lab_id']}_quiz.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            elif quiz_pdf_err:
                st.caption(quiz_pdf_err)

        with export_col3:
            rubric_pdf, rubric_pdf_err = _get_pdf_export(lab["lab_id"], "rubric")
            if rubric_pdf:
                st.download_button(
                    "Download Rubric PDF",
                    data=rubric_pdf,
                    file_name=f"{lab['lab_id']}_rubric.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            elif rubric_pdf_err:
                st.caption(rubric_pdf_err)

        _display_lab(lab)

        if lab.get("feedback_history"):
            st.divider()
            st.markdown("**Feedback history**")
            for entry in lab["feedback_history"]:
                st.markdown(
                    f"- v{entry['resulting_version']} · `{entry['requested_by']}`: {entry['feedback']}"
                )
    else:
        st.info("Fill in the form on the left and click **Generate** to see results here.")
