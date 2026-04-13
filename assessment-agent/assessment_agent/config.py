import os

# Grading weights (defaults -- can be overridden per-assignment via system_config.yaml)
CODE_GRADE_WEIGHT = 0.60
REPORT_GRADE_WEIGHT = 0.30
MANUAL_REVIEW_WEIGHT = 0.10

# Course
COURSE_ID = "CSC 580"

# LLM provider (override via DEFAULT_LLM_PROVIDER env var)
# Supported: "claude_cli", "anthropic"
DEFAULT_LLM_PROVIDER = os.environ.get("DEFAULT_LLM_PROVIDER", "claude_cli")

# LLM input truncation
MAX_REPORT_CHARS = 8000
MAX_CODE_CHARS = 8000

# Sandbox limits
SANDBOX_TIMEOUT_SECONDS = 30
SANDBOX_MEMORY_LIMIT_MB = 256
MAX_SUBMISSION_SIZE_MB = 10

# Paths
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = "/appdata" if os.environ.get("CONTAINER_APP_NAME") else os.path.dirname(_PACKAGE_DIR)
RESULTS_FILE = os.path.join(DATA_DIR, "assessment_results.json")
REVIEW_QUEUE_FILE = os.path.join(DATA_DIR, "review_queue.json")
ANOMALY_REPORTS_FILE = os.path.join(DATA_DIR, "anomaly_reports.json")
TEST_CASES_DIR = os.path.join(_PACKAGE_DIR, "test_cases")  # legacy location
ASSIGNMENTS_DIR = os.path.join(_PACKAGE_DIR, "assignments")
PROMPTS_DIR = os.path.join(_PACKAGE_DIR, "prompts")
