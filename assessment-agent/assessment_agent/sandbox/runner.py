import subprocess
import tempfile
import os
import time
from dataclasses import dataclass

from assessment_agent.config import SANDBOX_TIMEOUT_SECONDS


@dataclass
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: float
    timed_out: bool = False


# Imports that student code is NOT allowed to use
BLOCKED_IMPORTS = {
    "subprocess", "os", "sys", "shutil", "socket", "http",
    "urllib", "requests", "pathlib", "glob", "signal",
    "ctypes", "importlib", "code", "compile", "exec",
}


def check_code_safety(code: str) -> str | None:
    """Basic static check for dangerous patterns. Returns error message or None."""
    import ast
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"Syntax error: {e}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name.split(".")[0]
                if module in BLOCKED_IMPORTS:
                    return f"Blocked import: '{alias.name}' is not allowed in submissions"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module = node.module.split(".")[0]
                if module in BLOCKED_IMPORTS:
                    return f"Blocked import: '{node.module}' is not allowed in submissions"

    return None


def run_code(code: str, stdin_input: str = "", timeout: float = None) -> ExecutionResult:
    """Execute Python code in a sandboxed subprocess."""
    if timeout is None:
        timeout = SANDBOX_TIMEOUT_SECONDS

    # Safety check
    safety_error = check_code_safety(code)
    if safety_error:
        return ExecutionResult(
            stdout="",
            stderr=safety_error,
            exit_code=1,
            execution_time_ms=0,
            timed_out=False,
        )

    with tempfile.TemporaryDirectory(prefix="assess_") as tmpdir:
        code_file = os.path.join(tmpdir, "submission.py")
        with open(code_file, "w") as f:
            f.write(code)

        start = time.perf_counter()
        try:
            result = subprocess.run(
                ["python3", code_file],
                input=stdin_input,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
                env={
                    "PATH": os.environ.get("PATH", "/usr/bin:/usr/local/bin"),
                    "HOME": tmpdir,
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
            )
            elapsed = (time.perf_counter() - start) * 1000

            return ExecutionResult(
                stdout=result.stdout.strip(),
                stderr=result.stderr.strip(),
                exit_code=result.returncode,
                execution_time_ms=round(elapsed, 2),
            )

        except subprocess.TimeoutExpired:
            elapsed = (time.perf_counter() - start) * 1000
            return ExecutionResult(
                stdout="",
                stderr=f"Execution timed out after {timeout}s",
                exit_code=-1,
                execution_time_ms=round(elapsed, 2),
                timed_out=True,
            )
