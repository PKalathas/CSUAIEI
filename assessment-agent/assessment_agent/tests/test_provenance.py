"""
Tests for Ticket 9: Provenance Records.

Acceptance criteria under test:
  AC1 — Re-running a submission against the same code, prompts, and model produces
        an identical provenance record (modulo latency_ms).
  AC2 — Given a submission_id, the raw LLM output that produced each score is
        retrievable.
"""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from assessment_agent.models import (
    AssessmentRequest,
    AssessmentResult,
    LLMCallRecord,
    ProvenanceCollector,
    ProvenanceRecord,
    SubmissionType,
)
from assessment_agent.prompt_loader import load_prompt_with_hash
from assessment_agent.rubric import (
    _DEFAULT_RUBRIC_HASH,
    load_rubric_with_hash,
    parse_rubric_markdown,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _make_request(**kwargs) -> AssessmentRequest:
    return AssessmentRequest(student_id="s1", assignment_id="hw1_sorting", **kwargs)


SIMPLE_CODE = "def sort_list(lst):\n    return sorted(lst)\n"
SIMPLE_REPORT = "This report explains the sorting algorithm."


# ---------------------------------------------------------------------------
# 1. ProvenanceCollector unit tests
# ---------------------------------------------------------------------------

class TestProvenanceCollector:
    def _record(self, stage: str, latency: int = 100) -> LLMCallRecord:
        return LLMCallRecord(
            stage=stage,
            model_id="m",
            prompt_hash="ph",
            prompt_text="prompt",
            raw_response='{"ok": true}',
            latency_ms=latency,
        )

    def test_build_returns_provenance_record(self):
        c = ProvenanceCollector(model_id="m", rubric_hash="rh")
        assert isinstance(c.build(), ProvenanceRecord)

    def test_total_latency_sums_all_calls(self):
        c = ProvenanceCollector(model_id="m", rubric_hash="rh")
        c.add_call(self._record("a", 100))
        c.add_call(self._record("b", 250))
        assert c.build().total_latency_ms == 350

    def test_prompt_versions_keyed_by_stage(self):
        c = ProvenanceCollector(model_id="m", rubric_hash="rh")
        c.add_call(LLMCallRecord(
            stage="report_evaluation", model_id="m", prompt_hash="abc123",
            prompt_text="p", raw_response="r", latency_ms=10,
        ))
        assert c.build().prompt_versions["report_evaluation"] == "abc123"

    def test_failed_call_excluded_from_prompt_versions(self):
        c = ProvenanceCollector(model_id="m", rubric_hash="rh")
        c.add_call(LLMCallRecord(
            stage="anomaly_detection", model_id="m", prompt_hash="xyz",
            prompt_text="p", raw_response="", latency_ms=0,
            success=False, error="timeout",
        ))
        assert "anomaly_detection" not in c.build().prompt_versions

    def test_failed_call_still_in_llm_calls_list(self):
        c = ProvenanceCollector(model_id="m", rubric_hash="rh")
        c.add_call(LLMCallRecord(
            stage="anomaly_detection", model_id="m", prompt_hash="xyz",
            prompt_text="p", raw_response="", latency_ms=0,
            success=False, error="timeout",
        ))
        assert len(c.build().llm_calls) == 1
        assert c.build().llm_calls[0].success is False

    def test_input_hashes_propagated(self):
        c = ProvenanceCollector(
            model_id="m", rubric_hash="rh",
            code_hash="ch", report_hash="rph",
        )
        rec = c.build()
        assert rec.code_hash == "ch"
        assert rec.report_hash == "rph"
        assert rec.rubric_hash == "rh"
        assert rec.model_id == "m"

    def test_empty_collector_produces_valid_record(self):
        c = ProvenanceCollector(model_id="m", rubric_hash="rh")
        rec = c.build()
        assert rec.total_latency_ms == 0
        assert rec.llm_calls == []
        assert rec.prompt_versions == {}


# ---------------------------------------------------------------------------
# 2. load_prompt_with_hash unit tests
# ---------------------------------------------------------------------------

class TestLoadPromptWithHash:
    def test_returns_tuple_of_str_and_hex(self):
        text, h = load_prompt_with_hash(
            "report_evaluation", assignment_id=None,
            course_id="CS101", grading_guidance="",
            criteria_block="", criteria_json_template="", report_text="",
        )
        assert isinstance(text, str)
        assert isinstance(h, str)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_is_deterministic(self):
        kwargs = dict(
            assignment_id=None, course_id="CS101", grading_guidance="",
            criteria_block="", criteria_json_template="", report_text="test",
        )
        _, h1 = load_prompt_with_hash("report_evaluation", **kwargs)
        _, h2 = load_prompt_with_hash("report_evaluation", **kwargs)
        assert h1 == h2

    def test_different_variables_produce_different_hash(self):
        base = dict(
            assignment_id=None, course_id="CS101", grading_guidance="",
            criteria_block="", criteria_json_template="",
        )
        _, h1 = load_prompt_with_hash("report_evaluation", report_text="report A", **base)
        _, h2 = load_prompt_with_hash("report_evaluation", report_text="report B", **base)
        assert h1 != h2

    def test_hash_covers_rendered_prompt_not_template(self):
        # Same template, different substitution → different hash.
        _, h1 = load_prompt_with_hash(
            "report_evaluation", assignment_id=None,
            course_id="CLASS_A", grading_guidance="",
            criteria_block="", criteria_json_template="", report_text="",
        )
        _, h2 = load_prompt_with_hash(
            "report_evaluation", assignment_id=None,
            course_id="CLASS_B", grading_guidance="",
            criteria_block="", criteria_json_template="", report_text="",
        )
        assert h1 != h2


# ---------------------------------------------------------------------------
# 3. load_rubric_with_hash unit tests
# ---------------------------------------------------------------------------

class TestLoadRubricWithHash:
    def test_returns_tuple(self):
        rubric, h = load_rubric_with_hash("hw1_sorting")
        assert isinstance(h, str)
        assert len(h) == 64

    def test_known_assignment_hash_is_consistent(self):
        _, h1 = load_rubric_with_hash("hw1_sorting")
        _, h2 = load_rubric_with_hash("hw1_sorting")
        assert h1 == h2

    def test_unknown_assignment_returns_default_sentinel(self):
        _, h = load_rubric_with_hash("nonexistent_assignment_xyz")
        assert h == _DEFAULT_RUBRIC_HASH

    def test_default_sentinel_is_stable_hex(self):
        assert len(_DEFAULT_RUBRIC_HASH) == 64
        assert all(c in "0123456789abcdef" for c in _DEFAULT_RUBRIC_HASH)

    def test_different_assignments_produce_different_hashes(self):
        _, h1 = load_rubric_with_hash("hw1_sorting")
        _, h2 = load_rubric_with_hash("hw2_linked_list")
        assert h1 != h2


# ---------------------------------------------------------------------------
# 4. Agent-level provenance capture
# ---------------------------------------------------------------------------

class TestAgentProvenance:
    async def test_evaluate_report_adds_call_to_collector(self, fake_provider):
        from assessment_agent.agents.report_evaluator import evaluate_report
        collector = ProvenanceCollector(model_id=fake_provider.model_id, rubric_hash="rh")
        await evaluate_report(SIMPLE_REPORT, "hw1_sorting", provider=fake_provider, collector=collector)
        calls = collector.build().llm_calls
        assert len(calls) == 1
        assert calls[0].stage == "report_evaluation"

    async def test_evaluate_report_without_collector_does_not_error(self, fake_provider):
        from assessment_agent.agents.report_evaluator import evaluate_report
        result = await evaluate_report(SIMPLE_REPORT, "hw1_sorting", provider=fake_provider)
        assert result is not None

    async def test_detect_anomalies_adds_call_to_collector(self, fake_provider):
        from assessment_agent.agents.anomaly_detector import detect_anomalies
        collector = ProvenanceCollector(model_id=fake_provider.model_id, rubric_hash="rh")
        await detect_anomalies(SIMPLE_CODE, provider=fake_provider, collector=collector)
        calls = collector.build().llm_calls
        assert len(calls) == 1
        assert calls[0].stage == "anomaly_detection"

    async def test_generate_feedback_adds_call_to_collector(self, fake_provider):
        from assessment_agent.agents.feedback_generator import generate_feedback
        collector = ProvenanceCollector(model_id=fake_provider.model_id, rubric_hash="rh")
        await generate_feedback(
            student_id="s1", assignment_id="hw1_sorting",
            automated_score=75.0, code_grade=None, report_eval=None,
            anomaly=None, provider=fake_provider, collector=collector,
        )
        calls = collector.build().llm_calls
        assert len(calls) == 1
        assert calls[0].stage == "feedback_generation"

    async def test_agent_records_raw_response(self, fake_provider):
        from assessment_agent.agents.anomaly_detector import detect_anomalies
        collector = ProvenanceCollector(model_id=fake_provider.model_id, rubric_hash="rh")
        await detect_anomalies(SIMPLE_CODE, provider=fake_provider, collector=collector)
        raw = collector.build().llm_calls[0].raw_response
        assert isinstance(raw, str)
        assert len(raw) > 0

    async def test_agent_records_prompt_hash(self, fake_provider):
        from assessment_agent.agents.report_evaluator import evaluate_report
        collector = ProvenanceCollector(model_id=fake_provider.model_id, rubric_hash="rh")
        await evaluate_report(SIMPLE_REPORT, "hw1_sorting", provider=fake_provider, collector=collector)
        call = collector.build().llm_calls[0]
        assert len(call.prompt_hash) == 64
        assert call.prompt_hash == _sha256(call.prompt_text)

    async def test_agent_records_latency(self, fake_provider):
        from assessment_agent.agents.feedback_generator import generate_feedback
        collector = ProvenanceCollector(model_id=fake_provider.model_id, rubric_hash="rh")
        await generate_feedback(
            student_id="s1", assignment_id="hw1_sorting",
            automated_score=50.0, code_grade=None, report_eval=None,
            anomaly=None, provider=fake_provider, collector=collector,
        )
        assert collector.build().llm_calls[0].latency_ms == 50  # FakeLLMProvider returns 50


# ---------------------------------------------------------------------------
# 5. Orchestrator integration — provenance on AssessmentResult
# ---------------------------------------------------------------------------

class TestOrchestratorProvenance:
    async def test_provenance_is_attached_to_result(self, fake_provider, submissions):
        with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
            result = await _run(fake_provider, code=submissions["perfect_code"])
        assert result.provenance is not None

    async def test_code_hash_matches_submitted_code(self, fake_provider, submissions):
        code = submissions["perfect_code"]
        with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
            result = await _run(fake_provider, code=code)
        assert result.provenance.code_hash == _sha256(code)

    async def test_report_hash_matches_submitted_report(self, fake_provider, submissions):
        report = submissions["report"]
        with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
            result = await _run(fake_provider, report=report)
        assert result.provenance.report_hash == _sha256(report)

    async def test_code_hash_is_none_for_report_only(self, fake_provider, submissions):
        with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
            result = await _run(fake_provider, report=submissions["report"])
        assert result.provenance.code_hash is None

    async def test_model_id_matches_provider(self, fake_provider, submissions):
        with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
            result = await _run(fake_provider, code=submissions["perfect_code"])
        assert result.provenance.model_id == fake_provider.model_id

    async def test_rubric_hash_is_populated(self, fake_provider, submissions):
        with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
            result = await _run(fake_provider, code=submissions["perfect_code"])
        assert len(result.provenance.rubric_hash) == 64

    async def test_full_submission_has_four_llm_calls(self, fake_provider, submissions):
        # report_evaluation + anomaly_detection + orchestrator_reasoning + feedback_generation
        with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
            result = await _run(
                fake_provider,
                code=submissions["perfect_code"],
                report=submissions["report"],
            )
        assert len(result.provenance.llm_calls) == 4

    async def test_code_only_submission_has_three_llm_calls(self, fake_provider, submissions):
        # anomaly_detection + orchestrator_reasoning + feedback_generation
        with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
            result = await _run(fake_provider, code=submissions["perfect_code"])
        assert len(result.provenance.llm_calls) == 3

    async def test_report_only_submission_has_three_llm_calls(self, fake_provider, submissions):
        # report_evaluation + orchestrator_reasoning + feedback_generation
        with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
            result = await _run(fake_provider, report=submissions["report"])
        assert len(result.provenance.llm_calls) == 3

    async def test_all_llm_calls_have_nonempty_raw_response(self, fake_provider, submissions):
        """AC2: raw LLM output that produced each score is retrievable."""
        with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
            result = await _run(
                fake_provider,
                code=submissions["perfect_code"],
                report=submissions["report"],
            )
        for call in result.provenance.llm_calls:
            assert len(call.raw_response) > 0, f"Empty raw_response for stage {call.stage!r}"

    async def test_all_stages_covered_in_prompt_versions(self, fake_provider, submissions):
        with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
            result = await _run(
                fake_provider,
                code=submissions["perfect_code"],
                report=submissions["report"],
            )
        expected = {"report_evaluation", "anomaly_detection", "orchestrator_reasoning", "feedback_generation"}
        assert expected == set(result.provenance.prompt_versions.keys())

    async def test_total_latency_equals_sum_of_call_latencies(self, fake_provider, submissions):
        with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
            result = await _run(
                fake_provider,
                code=submissions["perfect_code"],
                report=submissions["report"],
            )
        prov = result.provenance
        assert prov.total_latency_ms == sum(c.latency_ms for c in prov.llm_calls)

    async def test_ac1_same_inputs_produce_same_hashes(self, fake_provider, submissions):
        """AC1: re-running same code+report+model produces identical provenance (modulo latency)."""
        code = submissions["perfect_code"]
        report = submissions["report"]

        with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
            r1 = await _run(fake_provider, code=code, report=report)
        with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
            r2 = await _run(fake_provider, code=code, report=report)

        p1, p2 = r1.provenance, r2.provenance
        assert p1.code_hash == p2.code_hash
        assert p1.report_hash == p2.report_hash
        assert p1.rubric_hash == p2.rubric_hash
        assert p1.model_id == p2.model_id
        assert p1.prompt_versions == p2.prompt_versions
        for c1, c2 in zip(p1.llm_calls, p2.llm_calls):
            assert c1.stage == c2.stage
            assert c1.prompt_hash == c2.prompt_hash
            assert c1.raw_response == c2.raw_response
            # latency_ms intentionally NOT compared (explicitly excluded by ticket)

    async def test_different_code_produces_different_code_hash(self, fake_provider, submissions):
        with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
            r1 = await _run(fake_provider, code=submissions["perfect_code"])
        with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
            r2 = await _run(fake_provider, code=submissions["buggy_code"])
        assert r1.provenance.code_hash != r2.provenance.code_hash

    async def test_orchestrator_reasoning_stage_present(self, fake_provider, submissions):
        """The orchestrator's own LLM call (the one most likely to be forgotten) is in provenance."""
        with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
            result = await _run(fake_provider, code=submissions["perfect_code"])
        stages = [c.stage for c in result.provenance.llm_calls]
        assert "orchestrator_reasoning" in stages


# ---------------------------------------------------------------------------
# 6. API — provenance endpoint logic
# ---------------------------------------------------------------------------

class TestProvenanceEndpoint:
    async def test_get_provenance_returns_record(self, fake_provider, submissions, tmp_path):
        """Provenance saved to results file is retrievable by submission_id."""
        from assessment_agent import config
        from assessment_agent.api.routes import _save_result, _get_results

        with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
            result = await _run(fake_provider, code=submissions["perfect_code"])

        _save_result(result)
        saved = _get_results()

        match = next((r for r in saved if r["submission_id"] == result.submission_id), None)
        assert match is not None
        assert match["provenance"] is not None
        assert match["provenance"]["code_hash"] == result.provenance.code_hash

    async def test_old_result_without_provenance_returns_none(self, tmp_path):
        """Results persisted before this ticket have provenance=None; endpoint must handle that."""
        import json as _json
        import assessment_agent.api.routes as _routes

        legacy = {
            "submission_id": "legacy01",
            "student_id": "s1",
            "assignment_id": "hw1_sorting",
            "automated_score": 70.0,
            "provenance": None,
        }

        # routes.RESULTS_FILE is a module-level name imported at load time, so
        # we patch it in place to point at a fresh temp file for this test.
        results_path = str(tmp_path / "legacy_results.json")
        with open(results_path, "w") as f:
            _json.dump([legacy], f)

        with patch.object(_routes, "RESULTS_FILE", results_path):
            results = _routes._get_results()

        match = next((r for r in results if r["submission_id"] == "legacy01"), None)
        assert match is not None, "legacy result not found in results file"
        assert match["provenance"] is None


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

async def _run(fake_provider, **kwargs) -> AssessmentResult:
    from assessment_agent.agents.orchestrator import assess_submission
    with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
        return await assess_submission(_make_request(**kwargs))
