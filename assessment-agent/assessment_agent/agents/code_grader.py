import json
import logging
import os

from assessment_agent.models import TestCase, TestCaseResult, CodeGradeResult
from assessment_agent.sandbox.runner import run_code
from assessment_agent.rubric import AssignmentRubric
from assessment_agent.prompt_loader import load_prompt
from assessment_agent.llm import LLMProvider
from assessment_agent import config

logger = logging.getLogger(__name__)

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


def _build_test_results_block(
    test_cases: list[TestCase],
    executions: list,  # list of ExecutionResult
) -> str:
    """Format test case executions into a human-readable block for the LLM."""
    lines = []
    for tc, ex in zip(test_cases, executions):
        status = "TIMED OUT" if ex.timed_out else ("ERROR" if ex.exit_code != 0 else "RAN OK")
        lines.append(
            f"Test: {tc.name} ({tc.points} pts)\n"
            f"  Input:    {tc.input!r}\n"
            f"  Expected: {tc.expected_output!r}\n"
            f"  Actual:   {ex.stdout!r}\n"
            f"  Status:   {status}"
            + (f"\n  Error:    {ex.stderr[:200]}" if ex.stderr else "")
        )
    return "\n\n".join(lines)


async def grade_code(
    code: str,
    assignment_id: str,
    rubric: AssignmentRubric | None = None,
    provider: LLMProvider | None = None,
) -> CodeGradeResult:
    """Run student code against test cases, then use an LLM to award partial credit."""
    if provider is None:
        from assessment_agent.llm import get_llm_provider
        provider = get_llm_provider()

    test_cases = load_test_cases(assignment_id)

    if not test_cases:
        return CodeGradeResult(
            compilation_error=f"No test cases found for assignment '{assignment_id}'"
        )

    # --- Step 1: Execute all test cases in the sandbox ---
    executions = []
    for tc in test_cases:
        executions.append(run_code(code, stdin_input=tc.input, timeout=tc.timeout_seconds))

    # --- Step 2: Ask the LLM to evaluate each result and award partial credit ---
    test_results_block = _build_test_results_block(test_cases, executions)

    prompt = load_prompt(
        "code_grading",
        assignment_id=assignment_id,
        course_id=config.COURSE_ID,
        grading_guidance=(rubric.guidance or "") if rubric else "",
        code=code[:config.MAX_CODE_CHARS],
        num_tests=len(test_cases),
        test_results_block=test_results_block,
    )

    try:
        llm_result = await provider.complete_json(prompt)
    except Exception:
        logger.warning("LLM code grading failed, falling back to exact-match", exc_info=True)
        llm_result = {}

    # Build a lookup: test_name -> credit_fraction from LLM response
    credit_map: dict[str, float] = {}
    for ev in llm_result.get("test_evaluations", []):
        name = ev.get("name", "")
        fraction = float(ev.get("credit_fraction", 0.0))
        credit_map[name] = max(0.0, min(1.0, fraction))

    # --- Step 3: Combine execution results with LLM credit fractions ---
    results = []
    total_points = 0.0
    earned_points = 0.0

    for tc, ex in zip(test_cases, executions):
        total_points += tc.points

        if credit_map:
            # LLM grading path: use the LLM-assigned credit fraction
            fraction = credit_map.get(tc.name, 0.0)
        else:
            # Fallback: exact string match (original behaviour)
            exact_match = (
                ex.exit_code == 0
                and ex.stdout.strip() == tc.expected_output.strip()
            )
            fraction = 1.0 if exact_match else 0.0

        points = round(tc.points * fraction, 2)
        earned_points += points

        results.append(TestCaseResult(
            name=tc.name,
            passed=fraction >= 1.0,
            expected_output=tc.expected_output,
            actual_output=ex.stdout,
            error=ex.stderr if fraction < 1.0 else "",
            execution_time_ms=ex.execution_time_ms,
            points_earned=points,
            points_possible=tc.points,
        ))

    raw_score = (earned_points / total_points * 100) if total_points > 0 else 0
    tests_passed = sum(1 for r in results if r.passed)

    return CodeGradeResult(
        test_results=results,
        tests_passed=tests_passed,
        tests_total=len(results),
        raw_score=round(raw_score, 2),
        weighted_score=round(raw_score * config.CODE_GRADE_WEIGHT, 2),
        runtime_errors=[r.error for r in results if r.error],
        llm_reasoning=llm_result.get("overall_reasoning", ""),
    )
