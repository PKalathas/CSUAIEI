"""
Rubric system: parse markdown rubric files into structured data.

Teachers write a simple rubric.md per assignment. The parser extracts
criteria, point values, and grading guidance into Pydantic models.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class RubricCriterion(BaseModel):
    name: str
    points: float
    description: str = ""
    weight: float = 0.0  # auto-derived: points / total_points


class AssignmentRubric(BaseModel):
    assignment_id: str = ""
    title: str = ""
    criteria: list[RubricCriterion] = []
    guidance: str = ""  # free-form grading philosophy text
    total_points: float = 0.0  # sum of all criteria points


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_rubric_markdown(text: str) -> AssignmentRubric:
    """Parse a rubric markdown file into an AssignmentRubric.

    Expected format:
        # Title
        ## Rubric
        | Criteria | Points | Description |
        |----------|--------|-------------|
        | ...      | ...    | ...         |

        ## Grading Guidance
        Free-form text ...
    """
    title = ""
    criteria: list[RubricCriterion] = []
    guidance = ""

    lines = text.split("\n")

    # ------------------------------------------------------------------
    # 1. Extract title from the first top-level header
    # ------------------------------------------------------------------
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            title = stripped[2:].strip()
            break

    # ------------------------------------------------------------------
    # 2. Find sections by ## headers
    # ------------------------------------------------------------------
    section_indices: dict[str, int] = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        match = re.match(r"^##\s+(.+)$", stripped)
        if match:
            section_name = match.group(1).strip().lower()
            section_indices[section_name] = i

    # ------------------------------------------------------------------
    # 3. Parse the Rubric table
    # ------------------------------------------------------------------
    rubric_start = section_indices.get("rubric")
    if rubric_start is not None:
        # Determine where the rubric section ends (next ## header or EOF)
        rubric_end = len(lines)
        for sec_name, idx in section_indices.items():
            if idx > rubric_start and idx < rubric_end:
                rubric_end = idx

        table_rows: list[str] = []
        for line in lines[rubric_start + 1 : rubric_end]:
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                table_rows.append(stripped)

        # Filter out header row and separator rows (contain ---)
        data_rows: list[str] = []
        for i, row in enumerate(table_rows):
            # Skip separator rows like |---|---|---|
            if re.match(r"^\|[\s\-|]+\|$", row):
                continue
            # Skip the first non-separator row (the column header)
            if i == 0:
                continue
            data_rows.append(row)

        for row in data_rows:
            # Split by | and strip; ignore leading/trailing empty strings
            cells = [cell.strip() for cell in row.split("|")]
            # Splitting "| A | B | C |" gives ['', 'A', 'B', 'C', '']
            cells = [c for c in cells if c != "" or False]
            # Filter truly empty strings from split artifacts
            cells = [c for c in cells]

            if len(cells) < 2:
                continue

            name = cells[0].strip()
            if not name:
                continue

            # Parse points
            try:
                points = float(cells[1].strip())
            except (ValueError, IndexError):
                logger.warning("Could not parse points for criterion %r, skipping", name)
                continue

            description = cells[2].strip() if len(cells) > 2 else ""

            criteria.append(RubricCriterion(
                name=name,
                points=points,
                description=description,
            ))

    # ------------------------------------------------------------------
    # 4. Parse the Grading Guidance section
    # ------------------------------------------------------------------
    guidance_start = section_indices.get("grading guidance")
    if guidance_start is not None:
        # Determine where guidance section ends (next ## header or EOF)
        guidance_end = len(lines)
        for sec_name, idx in section_indices.items():
            if idx > guidance_start and idx < guidance_end:
                guidance_end = idx

        guidance_lines = lines[guidance_start + 1 : guidance_end]
        guidance = "\n".join(guidance_lines).strip()

    # ------------------------------------------------------------------
    # 5. Calculate total_points and per-criterion weights
    # ------------------------------------------------------------------
    total_points = sum(c.points for c in criteria)

    if total_points > 0:
        for c in criteria:
            c.weight = round(c.points / total_points, 4)

    return AssignmentRubric(
        title=title,
        criteria=criteria,
        guidance=guidance,
        total_points=total_points,
    )


# ---------------------------------------------------------------------------
# Default rubric (backward compatibility)
# ---------------------------------------------------------------------------


def default_rubric() -> AssignmentRubric:
    """Return the original hardcoded rubric for backward compatibility.

    Matches the four criteria previously hardcoded in report_evaluator.py:
    Logical Clarity, Completeness, Technical Accuracy, Writing Quality.
    """
    criteria = [
        RubricCriterion(name="Logical Clarity", points=25, description="Is the reasoning well-structured?"),
        RubricCriterion(name="Completeness", points=25, description="Addresses all required aspects?"),
        RubricCriterion(name="Technical Accuracy", points=25, description="Are technical claims correct?"),
        RubricCriterion(name="Writing Quality", points=25, description="Grammar, formatting, readability"),
    ]
    total_points = sum(c.points for c in criteria)
    for c in criteria:
        c.weight = round(c.points / total_points, 4)

    return AssignmentRubric(
        title="Default Rubric",
        criteria=criteria,
        guidance="",
        total_points=total_points,
    )


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

# Package directory – used to resolve assignment paths
_PACKAGE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))


def load_rubric(assignment_id: str) -> AssignmentRubric:
    """Load a rubric for the given assignment.

    Looks for ``assignments/{assignment_id}/rubric.md`` relative to the
    assessment_agent package directory. Falls back to ``default_rubric()``
    if the file is not found.
    """
    rubric_path = _PACKAGE_DIR / "assignments" / assignment_id / "rubric.md"

    if rubric_path.is_file():
        logger.info("Loading rubric from %s", rubric_path)
        text = rubric_path.read_text(encoding="utf-8")
        rubric = parse_rubric_markdown(text)
        rubric.assignment_id = assignment_id
        return rubric

    logger.info(
        "No rubric.md found for assignment %r at %s; using default rubric",
        assignment_id,
        rubric_path,
    )
    rubric = default_rubric()
    rubric.assignment_id = assignment_id
    return rubric
