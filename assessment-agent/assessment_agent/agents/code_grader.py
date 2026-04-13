import json
import os

from assessment_agent.models import TestCase, TestCaseResult, CodeGradeResult
from assessment_agent.sandbox.runner import run_code
from assessment_agent.rubric import AssignmentRubric
from assessment_agent import config


# Paths for both old and new assignment directory layouts
_PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ASSIGNMENTS_DIR = os.path.join(_PACKAGE_DIR, "assessment_agent", "assignments")


def load_test_cases(assignment_id: str) -> list[TestCase]:
    """Load test cases for an assignment from JSON file.

    Checks the new assignments/ directory first, falls back to the
    legacy test_cases/ directory.
    """
    # New location: assignments/{assignment_id}/test_cases.json
    new_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assignments", assignment_id, "test_cases.json",
    )
    # Legacy location: test_cases/{assignment_id}.json
    legacy_path = os.path.join(config.TEST_CASES_DIR, f"{assignment_id}.json")

    test_file = None
    if os.path.exists(new_path):
        test_file = new_path
    elif os.path.exists(legacy_path):
        test_file = legacy_path

    if not test_file:
        return []

    with open(test_file) as f:
        data = json.load(f)

    return [TestCase(**tc) for tc in data.get("test_cases", [])]


def get_available_assignments() -> list[dict]:
    """List all assignments that have test cases.

    Checks both new assignments/ directory and legacy test_cases/ directory.
    """
    assignments = []
    seen_ids = set()

    # Check new assignments/ directory
    assignments_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assignments",
    )
    if os.path.exists(assignments_dir):
        for entry in os.listdir(assignments_dir):
            tc_path = os.path.join(assignments_dir, entry, "test_cases.json")
            if os.path.isfile(tc_path):
                with open(tc_path) as f:
                    data = json.load(f)
                aid = data.get("assignment_id", entry)
                seen_ids.add(aid)
                assignments.append({
                    "assignment_id": aid,
                    "title": data.get("title", entry),
                    "num_test_cases": len(data.get("test_cases", [])),
                    "total_points": sum(tc.get("points", 10) for tc in data.get("test_cases", [])),
                })

    # Check legacy test_cases/ directory
    if os.path.exists(config.TEST_CASES_DIR):
        for filename in os.listdir(config.TEST_CASES_DIR):
            if filename.endswith(".json"):
                filepath = os.path.join(config.TEST_CASES_DIR, filename)
                with open(filepath) as f:
                    data = json.load(f)
                aid = data.get("assignment_id", filename.replace(".json", ""))
                if aid not in seen_ids:
                    assignments.append({
                        "assignment_id": aid,
                        "title": data.get("title", filename.replace(".json", "")),
                        "num_test_cases": len(data.get("test_cases", [])),
                        "total_points": sum(tc.get("points", 10) for tc in data.get("test_cases", [])),
                    })

    return assignments


def grade_code(
    code: str,
    assignment_id: str,
    rubric: AssignmentRubric | None = None,
) -> CodeGradeResult:
    """Run student code against test cases and produce a grade."""
    test_cases = load_test_cases(assignment_id)

    if not test_cases:
        return CodeGradeResult(
            compilation_error=f"No test cases found for assignment '{assignment_id}'"
        )

    results = []
    total_points = 0
    earned_points = 0

    for tc in test_cases:
        total_points += tc.points
        execution = run_code(code, stdin_input=tc.input, timeout=tc.timeout_seconds)

        passed = (
            execution.exit_code == 0
            and execution.stdout.strip() == tc.expected_output.strip()
        )

        points = tc.points if passed else 0.0
        earned_points += points

        results.append(TestCaseResult(
            name=tc.name,
            passed=passed,
            expected_output=tc.expected_output,
            actual_output=execution.stdout,
            error=execution.stderr if not passed else "",
            execution_time_ms=execution.execution_time_ms,
            points_earned=points,
            points_possible=tc.points,
        ))

    raw_score = (earned_points / total_points * 100) if total_points > 0 else 0
    tests_passed = sum(1 for r in results if r.passed)

    code_weight = config.CODE_GRADE_WEIGHT

    return CodeGradeResult(
        test_results=results,
        tests_passed=tests_passed,
        tests_total=len(results),
        raw_score=round(raw_score, 2),
        weighted_score=round(raw_score * code_weight, 2),
        runtime_errors=[r.error for r in results if r.error],
    )
