import json
from pathlib import Path
from unittest.mock import patch
 
import pytest
 
from assessment_agent.agents.orchestrator import assess_submission
from assessment_agent.models import AssessmentRequest, SubmissionType
 
 
def make_request(**kwargs) -> AssessmentRequest:
   return AssessmentRequest(student_id="test_student", assignment_id="hw1_sorting", **kwargs)
 
 
async def test_code_only_submission(fake_provider, submissions):
   with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
       result = await assess_submission(make_request(code=submissions["perfect_code"]))
   assert result.code_grade is not None
   assert result.report_evaluation is None
   assert result.submission_type == SubmissionType.CODE_ONLY
 
 
async def test_report_only_submission(fake_provider, submissions):
   with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
       result = await assess_submission(make_request(report=submissions["report"]))
   assert result.report_evaluation is not None
   assert result.code_grade is None
   assert result.submission_type == SubmissionType.REPORT_ONLY
 
 
async def test_full_submission(fake_provider, submissions):
   with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
       result = await assess_submission(
           make_request(code=submissions["perfect_code"], report=submissions["report"])
       )
   assert result.code_grade is not None
   assert result.report_evaluation is not None
   assert result.submission_type == SubmissionType.FULL
   assert 0.0 <= result.automated_score <= 90.0
   assert result.feedback is not None
   assert result.manual_review is not None
 
 
async def test_review_queue_written(fake_provider, submissions, data_dir: Path):
   with patch("assessment_agent.agents.orchestrator.get_llm_provider", return_value=fake_provider):
       await assess_submission(make_request(code=submissions["perfect_code"]))
   queue_file = data_dir / "review_queue.json"
   assert queue_file.exists()
   entries = json.loads(queue_file.read_text())
   assert len(entries) > 0