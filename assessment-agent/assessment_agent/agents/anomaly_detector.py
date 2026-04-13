import ast
import json
import logging

from assessment_agent.models import AnomalyReport, AnomalyFlag
from assessment_agent.llm import LLMProvider
from assessment_agent.rubric import AssignmentRubric
from assessment_agent.prompt_loader import load_prompt
from assessment_agent import config

logger = logging.getLogger(__name__)


def extract_style_metrics(code: str) -> dict:
    """Extract code style fingerprint using AST analysis."""
    metrics = {
        "num_functions": 0,
        "num_classes": 0,
        "num_imports": 0,
        "avg_line_length": 0,
        "max_line_length": 0,
        "num_comments": 0,
        "naming_conventions": [],
        "complexity_indicators": 0,
        "total_lines": 0,
        "blank_lines": 0,
    }

    lines = code.split("\n")
    metrics["total_lines"] = len(lines)
    metrics["blank_lines"] = sum(1 for l in lines if not l.strip())
    line_lengths = [len(l) for l in lines if l.strip()]
    metrics["avg_line_length"] = round(sum(line_lengths) / max(len(line_lengths), 1), 1)
    metrics["max_line_length"] = max(line_lengths) if line_lengths else 0
    metrics["num_comments"] = sum(1 for l in lines if l.strip().startswith("#"))

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return metrics

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            metrics["num_functions"] += 1
            metrics["naming_conventions"].append(
                "snake_case" if "_" in node.name else "camelCase" if node.name[0].islower() else "PascalCase"
            )
        elif isinstance(node, ast.ClassDef):
            metrics["num_classes"] += 1
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            metrics["num_imports"] += 1
        elif isinstance(node, ast.For):
            for child in ast.walk(node):
                if isinstance(child, ast.For) and child is not node:
                    metrics["complexity_indicators"] += 1
        elif isinstance(node, ast.ListComp):
            metrics["complexity_indicators"] += 1

    return metrics


async def detect_anomalies(
    code: str,
    student_id: str = "",
    rubric: AssignmentRubric | None = None,
    provider: LLMProvider | None = None,
) -> AnomalyReport:
    """Analyze code for style anomalies and potential academic integrity issues."""
    if rubric is None:
        from assessment_agent.rubric import default_rubric
        rubric = default_rubric()
    if provider is None:
        from assessment_agent.llm import get_llm_provider
        provider = get_llm_provider()

    metrics = extract_style_metrics(code)

    prompt = load_prompt(
        "anomaly_detection",
        assignment_id=rubric.assignment_id,
        course_id=config.COURSE_ID,
        grading_guidance=rubric.guidance or "",
        metrics=json.dumps(metrics, indent=2),
        code=code[:config.MAX_CODE_CHARS],
    )

    try:
        result = await provider.complete_json(prompt)
    except Exception:
        logger.warning("Anomaly detection failed", exc_info=True)
        return AnomalyReport(recommendation="Failed to analyze submission.")

    flags = []
    for f in result.get("flags", []):
        flags.append(AnomalyFlag(
            flag_type=f.get("flag_type", "unknown"),
            confidence=min(max(float(f.get("confidence", 0)), 0), 1),
            evidence=f.get("evidence", ""),
            severity=f.get("severity", "low"),
        ))

    return AnomalyReport(
        flags=flags,
        overall_risk=result.get("overall_risk", "low"),
        recommendation=result.get("recommendation", ""),
    )
