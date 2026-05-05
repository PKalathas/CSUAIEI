from assessment_agent.rubric import parse_rubric_markdown
 
VALID_RUBRIC_MD = """\
# HW1: Sorting Algorithms
 
## Rubric
 
| Criteria     | Points | Description               |
|--------------|--------|---------------------------|
| Correctness  | 50     | Passes all test cases     |
| Code Quality | 25     | Readable, well-commented  |
| Efficiency   | 15     | Appropriate complexity    |
| Docs         | 10     | Report explains approach  |
 
## Grading Guidance
 
Focus on correctness first. Partial credit allowed.
"""
 
MALFORMED_TABLE_MD = """\
# Bad Points Rubric
 
## Rubric
 
| Criteria  | Points | Description  |
|-----------|--------|--------------|
| Good Row  | 30     | This is fine |
| Bad Row   | oops   | Not a number |
 
## Grading Guidance
 
Some guidance.
"""
 
 
def test_happy_path_title():
   assert parse_rubric_markdown(VALID_RUBRIC_MD).title == "HW1: Sorting Algorithms"
 
 
def test_happy_path_criteria_count():
   assert len(parse_rubric_markdown(VALID_RUBRIC_MD).criteria) == 4
 
 
def test_happy_path_points():
   rubric = parse_rubric_markdown(VALID_RUBRIC_MD)
   assert [c.points for c in rubric.criteria] == [50.0, 25.0, 15.0, 10.0]
 
 
def test_happy_path_total_points():
   assert parse_rubric_markdown(VALID_RUBRIC_MD).total_points == 100.0
 
 
def test_happy_path_weights_sum_to_one():
   rubric = parse_rubric_markdown(VALID_RUBRIC_MD)
   assert abs(sum(c.weight for c in rubric.criteria) - 1.0) < 1e-4
 
 
def test_happy_path_guidance():
   assert "correctness" in parse_rubric_markdown(VALID_RUBRIC_MD).guidance.lower()
 
 
def test_malformed_bad_row_skipped():
   rubric = parse_rubric_markdown(MALFORMED_TABLE_MD)
   assert not any(c.name == "Bad Row" for c in rubric.criteria)
 
 
def test_malformed_good_row_kept():
   rubric = parse_rubric_markdown(MALFORMED_TABLE_MD)
   assert any(c.name == "Good Row" for c in rubric.criteria)
 
 
def test_malformed_does_not_raise():
   parse_rubric_markdown(MALFORMED_TABLE_MD)