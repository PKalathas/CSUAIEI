"""
AIEIC Assessment Agent — Demo Script

Demonstrates the full assessment pipeline with 4 mock student submissions:
  1. Alice  — Perfect code + report (full submission)
  2. Bob    — Buggy code (lexicographic sort)
  3. Carol  — Suspiciously advanced code (anomaly detection)
  4. Diana  — Partial solution (bubble sort, works but bare-except)

Run:
    source .venv/bin/activate
    python demo/run_demo.py
"""
import asyncio
import os
import sys
import json
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assessment_agent.models import AssessmentRequest
from assessment_agent.agents.orchestrator import assess_submission
from assessment_agent.agents.code_grader import grade_code

DEMO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "submissions")

# ─────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────

BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def header(text):
    print(f"\n{BOLD}{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}{RESET}\n")


def section(text):
    print(f"\n{BOLD}{BLUE}--- {text} ---{RESET}")


def ok(text):
    print(f"  {GREEN}✓{RESET} {text}")


def warn(text):
    print(f"  {YELLOW}⚠{RESET} {text}")


def fail(text):
    print(f"  {RED}✗{RESET} {text}")


def info(text):
    print(f"  {DIM}{text}{RESET}")


def read_file(name):
    with open(os.path.join(DEMO_DIR, name)) as f:
        return f.read()


# ─────────────────────────────────────────────
# Demo 1: Code-only grading (LLM-based)
# ─────────────────────────────────────────────

async def demo_code_grading():
    header("DEMO 1: Code Grading (LLM-based partial credit)")
    print("Runs code in sandbox, then asks Claude to award partial credit per test.\n")

    submissions = [
        ("Alice (perfect)", "student_a_perfect.py"),
        ("Bob (buggy)", "student_b_buggy.py"),
        ("Carol (suspicious)", "student_c_suspicious.py"),
        ("Diana (partial)", "student_d_partial.py"),
    ]

    for name, filename in submissions:
        code = read_file(filename)
        start = time.time()
        grade = await grade_code(code, "hw1_sorting")
        elapsed = time.time() - start

        section(f"{name}: {filename}")
        print(f"  Tests: {grade.tests_passed}/{grade.tests_total} passed")
        print(f"  Raw score: {grade.raw_score}/100")
        print(f"  Weighted (60%): {BOLD}{grade.weighted_score}/60{RESET}")
        print(f"  Time: {elapsed:.1f}s")

        for tr in grade.test_results:
            if tr.passed:
                ok(f"{tr.name} ({tr.points_earned}/{tr.points_possible} pts)")
            else:
                fail(f"{tr.name} — expected: '{tr.expected_output[:40]}', got: '{tr.actual_output[:40]}'")

        if grade.llm_reasoning:
            info(f"LLM: {grade.llm_reasoning[:120]}")

        if grade.runtime_errors:
            for err in grade.runtime_errors[:2]:
                warn(f"Error: {err[:80]}")


# ─────────────────────────────────────────────
# Demo 2: Full agentic assessment (uses Claude)
# ─────────────────────────────────────────────

async def demo_full_assessment(student_name, code_file, report_file=None):
    code = read_file(code_file)
    report = read_file(report_file) if report_file else None

    student_id = student_name.lower().replace(" ", "_")
    request = AssessmentRequest(
        student_id=student_id,
        assignment_id="hw1_sorting",
        code=code,
        report=report,
    )

    section(f"Assessing {student_name}...")
    start = time.time()
    result = await assess_submission(request)
    elapsed = time.time() - start

    print(f"  Submission ID: {result.submission_id}")
    print(f"  Time: {elapsed:.1f}s")

    # Code grade
    if result.code_grade:
        cg = result.code_grade
        print(f"\n  {BOLD}Code Grade:{RESET} {cg.weighted_score}/60 ({cg.tests_passed}/{cg.tests_total} tests)")

    # Report grade
    if result.report_evaluation:
        re = result.report_evaluation
        print(f"  {BOLD}Report Grade:{RESET} {re.weighted_score}/30")
        for c in re.criteria:
            print(f"    {c.name}: {c.score}/{c.max_score} — {c.justification}")

    # Anomalies
    if result.anomaly_report:
        ar = result.anomaly_report
        risk_color = RED if ar.overall_risk == "high" else YELLOW if ar.overall_risk == "medium" else GREEN
        print(f"\n  {BOLD}Anomaly Check:{RESET} {risk_color}{ar.overall_risk.upper()}{RESET} risk")
        if ar.flags:
            for f in ar.flags:
                flag_fn = warn if f.severity == "medium" else fail if f.severity == "high" else info
                flag_fn(f"{f.flag_type} ({f.confidence:.0%}): {f.evidence}")
        else:
            ok("No flags raised")

    # Score
    print(f"\n  {BOLD}Automated Score: {result.automated_score}/90{RESET}")

    # Agent reasoning
    if result.agent_reasoning:
        print(f"\n  {BOLD}Agent Reasoning:{RESET}")
        for line in result.agent_reasoning.split(". "):
            info(line.strip() + ("." if not line.endswith(".") else ""))

    # Feedback
    if result.feedback and result.feedback.summary:
        fb = result.feedback
        print(f"\n  {BOLD}Feedback:{RESET}")
        info(fb.summary)
        if fb.strengths:
            print(f"\n  {GREEN}Strengths:{RESET}")
            for s in fb.strengths:
                ok(s)
        if fb.improvements:
            print(f"\n  {YELLOW}Improvements:{RESET}")
            for i in fb.improvements:
                warn(i)
        if fb.next_steps:
            print(f"\n  {BLUE}Next Steps:{RESET}")
            for n in fb.next_steps:
                info(f"→ {n}")

    # Review queue
    if result.manual_review:
        mr = result.manual_review
        print(f"\n  {BOLD}Instructor Review:{RESET} priority={mr.priority}")
        if mr.instructor_notes:
            info(f"Notes: {mr.instructor_notes}")

    return result


async def demo_agentic_pipeline():
    header("DEMO 2: Full Agentic Assessment (Claude CLI)")
    print("Each submission spawns 4 Claude calls: code grading + anomaly + reasoning + feedback\n")

    results = []

    # Bob — buggy code, no report
    r = await demo_full_assessment("Bob", "student_b_buggy.py")
    results.append(r)

    # Carol — suspicious code, no report
    r = await demo_full_assessment("Carol", "student_c_suspicious.py")
    results.append(r)

    # Alice — perfect code + report (full submission)
    r = await demo_full_assessment("Alice", "student_a_perfect.py", "student_a_report.md")
    results.append(r)

    return results


# ─────────────────────────────────────────────
# Demo 3: Show API / data artifacts
# ─────────────────────────────────────────────

def demo_data_artifacts():
    header("DEMO 3: Data Artifacts (Review Queue + Anomaly Reports)")

    from assessment_agent.interfaces.instructor_copilot import get_review_queue
    from assessment_agent.interfaces.integrity_guardian import get_anomaly_reports

    queue = get_review_queue()
    section(f"Instructor Review Queue ({len(queue)} items)")
    for item in queue:
        priority_color = RED if item["priority"] == "urgent" else YELLOW if item["priority"] == "high" else RESET
        print(f"  [{priority_color}{item['priority'].upper()}{RESET}] {item['student_id']} — {item['assignment_id']} — score: {item['automated_score']}")
        if item.get("instructor_notes"):
            info(f"  Notes: {item['instructor_notes'][:100]}")

    reports = get_anomaly_reports()
    section(f"Anomaly Reports ({len(reports)} items)")
    if not reports:
        ok("No anomalies flagged")
    for report in reports:
        risk_color = RED if report["overall_risk"] == "high" else YELLOW
        print(f"  [{risk_color}{report['overall_risk'].upper()}{RESET}] {report['student_id']} — {report['assignment_id']}")
        for flag in report.get("flags", []):
            warn(f"  {flag['flag_type']} ({flag['confidence']:.0%}): {flag['evidence'][:80]}")


# ─────────────────────────────────────────────
# Demo 4: Instructor completes a review
# ─────────────────────────────────────────────

def demo_instructor_review(submission_id):
    header("DEMO 4: Instructor Completes Manual Review")

    from assessment_agent.interfaces.instructor_copilot import complete_review

    section(f"Completing review for {submission_id}")
    print(f"  Instructor score: 8/10 (innovation & depth)")
    print(f"  Notes: 'Good understanding of the core concept'\n")

    found = complete_review(submission_id, instructor_score=8.0, notes="Good understanding of the core concept")
    if found:
        ok(f"Review completed! Final score = automated + (8 × 10%) = automated + 8 points")
    else:
        fail(f"Submission {submission_id} not found in queue")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

async def main():
    print(f"\n{BOLD}{'╔' + '═' * 58 + '╗'}")
    print(f"{'║'} {'AIEIC Assessment Agent — Demo':^56} {'║'}")
    print(f"{'║'} {'CSC 580 Lab Agentic Design Framework':^56} {'║'}")
    print(f"{'╚' + '═' * 58 + '╝'}{RESET}")

    # Demo 1: LLM-based code grading
    await demo_code_grading()

    input(f"\n{DIM}Press Enter to run full agentic assessment (uses Claude CLI)...{RESET}")

    # Demo 2: Full agentic pipeline with Claude
    results = await demo_agentic_pipeline()

    # Demo 3: Show persisted data
    demo_data_artifacts()

    # Demo 4: Instructor review
    if results:
        demo_instructor_review(results[0].submission_id)

    header("Demo Complete")
    print("All assessment results saved to: assessment_results.json")
    print("Review queue saved to: review_queue.json")
    print("Anomaly reports saved to: anomaly_reports.json")
    print(f"\nAPI endpoints available when server is running:")
    print(f"  GET  /api/assess/assignments")
    print(f"  POST /api/assess/submit-json")
    print(f"  GET  /api/assess/results")
    print(f"  GET  /api/assess/review-queue")
    print(f"  GET  /api/assess/anomalies")
    print(f"  POST /api/assess/review-queue/{{id}}/complete\n")


if __name__ == "__main__":
    # Clean previous demo data
    for f in ["assessment_results.json", "review_queue.json", "anomaly_reports.json"]:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), f)
        if os.path.exists(path):
            os.remove(path)

    asyncio.run(main())
