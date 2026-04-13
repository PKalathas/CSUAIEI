"""
Prompt loader utility for the assessment agent.

Loads prompt templates from disk and substitutes variables using
string.Template.  Supports per-assignment overrides: if a file exists at
    assignments/{assignment_id}/prompts/{name}.txt
it is used instead of the default
    prompts/{name}.txt

All templates use ${variable} syntax.  safe_substitute is used so that
any variables not provided are left as-is (important during the
incremental migration to external templates).
"""

from string import Template
import os

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")
ASSIGNMENTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assignments")


def load_prompt(name: str, assignment_id: str | None = None, **kwargs) -> str:
    """
    Load a prompt template and substitute variables.

    Looks for an assignment-specific override first:
        assignments/{assignment_id}/prompts/{name}.txt
    Falls back to the default:
        prompts/{name}.txt

    Uses string.Template with ${variable} substitution.

    Parameters
    ----------
    name : str
        Base name of the template file (without the .txt extension).
    assignment_id : str | None
        Optional assignment identifier.  When provided, the loader checks
        for an assignment-specific override before falling back to the
        default template.
    **kwargs
        Variable substitutions to apply to the template.

    Returns
    -------
    str
        The fully-substituted prompt string.

    Raises
    ------
    FileNotFoundError
        If no template file can be found for the given name.
    """
    template_path = None

    # 1. Check for assignment-specific override
    if assignment_id:
        override = os.path.join(ASSIGNMENTS_DIR, assignment_id, "prompts", f"{name}.txt")
        if os.path.isfile(override):
            template_path = override

    # 2. Fall back to the default template
    if template_path is None:
        default = os.path.join(PROMPTS_DIR, f"{name}.txt")
        if os.path.isfile(default):
            template_path = default

    if template_path is None:
        raise FileNotFoundError(
            f"Prompt template '{name}' not found.  "
            f"Searched: prompts/{name}.txt"
            + (f" and assignments/{assignment_id}/prompts/{name}.txt" if assignment_id else "")
        )

    with open(template_path, "r", encoding="utf-8") as fh:
        content = fh.read()

    return Template(content).safe_substitute(**kwargs)
