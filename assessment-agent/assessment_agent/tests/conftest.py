import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

_REPO_ROOT = Path(__file__).parent.parent.parent  # assessment_agent/tests/ → assessment_agent/ → project root
_SUBMISSIONS_DIR = _REPO_ROOT / "demo" / "submissions"


class FakeLLMProvider:
    model_id: str = "fake-model-v1"

    _CANNED: list[tuple[str, dict]] = [
        ("BEGIN STUDENT REPORT", {
            "criteria": [
                {"name": "Logical Clarity",   "score": 8, "justification": "Well structured argument."},
                {"name": "Completeness",       "score": 9, "justification": "All aspects addressed."},
                {"name": "Technical Accuracy", "score": 7, "justification": "Minor inaccuracies."},
                {"name": "Writing Quality",    "score": 9, "justification": "Clear prose."},
            ],
            "reasoning": "Solid report with minor technical gaps.",
        }),
        ("academic integrity analyst", {
            "flags": [],
            "overall_risk": "low",
            "recommendation": "No concerns detected.",
        }),
        ("supportive but rigorous", {
            "summary": "Good work overall.",
            "strengths": ["Correct output", "Clean code"],
            "improvements": ["Add comments"],
            "next_steps": ["Try edge cases"],
        }),
        ("Assessment Orchestrator", {
            "reasoning": "Score looks appropriate.",
            "score_adjustment": 0,
            "review_priority": "normal",
            "instructor_notes": "No issues.",
        }),
    ]

    async def complete(self, prompt: str, system: str = "") -> str:
        return json.dumps(self._dispatch(prompt))

    async def complete_with_raw(self, prompt: str, system: str = "") -> tuple[dict, str, int]:
        result = self._dispatch(prompt)
        return result, json.dumps(result), 50

    async def complete_json(self, prompt: str, system: str = "") -> dict:
        return self._dispatch(prompt)

    def _dispatch(self, prompt: str) -> dict:
        for keyword, response in self._CANNED:
            if keyword in prompt:
                return response
        return {
            "reasoning": "fallback",
            "score_adjustment": 0,
            "review_priority": "normal",
            "instructor_notes": "",
        }


@pytest.fixture
def fake_provider() -> FakeLLMProvider:
    return FakeLLMProvider()


@pytest.fixture(autouse=True)
def data_dir(tmp_path: Path):
    """Redirect all file output to a temp directory via environment variable."""
    old = os.environ.get("DATA_DIR")
    os.environ["DATA_DIR"] = str(tmp_path)

    import assessment_agent.config as cfg
    cfg.DATA_DIR             = str(tmp_path)
    cfg.RESULTS_FILE         = str(tmp_path / "assessment_results.json")
    cfg.REVIEW_QUEUE_FILE    = str(tmp_path / "review_queue.json")
    cfg.ANOMALY_REPORTS_FILE = str(tmp_path / "anomaly_reports.json")

    import assessment_agent.interfaces.instructor_copilot as ic
    import assessment_agent.interfaces.integrity_guardian as ig
    ic.REVIEW_QUEUE_FILE    = str(tmp_path / "review_queue.json")
    ig.ANOMALY_REPORTS_FILE = str(tmp_path / "anomaly_reports.json")

    yield tmp_path

    if old is None:
        os.environ.pop("DATA_DIR", None)
    else:
        os.environ["DATA_DIR"] = old


@pytest.fixture(scope="session")
def submissions() -> dict[str, str]:
    def read(name: str) -> str:
        return (_SUBMISSIONS_DIR / name).read_text(encoding="utf-8")

    return {
        "perfect_code":    read("student_a_perfect.py"),
        "report":          read("student_a_report.md"),
        "buggy_code":      read("student_b_buggy.py"),
        "suspicious_code": read("student_c_suspicious.py"),
        "partial_code":    read("student_d_partial.py"),
    }
