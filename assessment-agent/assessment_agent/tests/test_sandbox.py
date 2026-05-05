import pytest
from assessment_agent.sandbox.runner import check_code_safety, BLOCKED_IMPORTS
 
 
def test_clean_code_allowed():
   assert check_code_safety("x = sorted([3, 1, 2])") is None
 
 
def test_allowed_import_math():
   assert check_code_safety("import math") is None
 
 
def test_allowed_from_collections():
   assert check_code_safety("from collections import defaultdict") is None
 
 
@pytest.mark.parametrize("module", sorted(BLOCKED_IMPORTS))
def test_direct_import_blocked(module):
   result = check_code_safety(f"import {module}")
   assert result is not None
   assert "Blocked import" in result
 
 
@pytest.mark.parametrize("module", sorted(BLOCKED_IMPORTS))
def test_from_import_blocked(module):
   result = check_code_safety(f"from {module} import something")
   assert result is not None
   assert "Blocked import" in result
 
 
def test_submodule_import_blocked():
   assert check_code_safety("import os.path") is not None
 
 
def test_syntax_error_returns_error_string():
   result = check_code_safety("def broken(\n    pass")
   assert result is not None
   assert "yntax" in result