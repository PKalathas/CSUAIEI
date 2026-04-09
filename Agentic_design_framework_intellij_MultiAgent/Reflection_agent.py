from base_agent import BaseAgent

"""
    Agent for reflecting and improving the medical assessment of the Prompt_processing_agent
"""
class Reflection_agent(BaseAgent):
    def __init__(self, system_message, instructions):
        super().__init__(
            name = "critic_agent",
            role = "Assessment Critic",
            instructions = instructions,
            system_message = system_message
        )
        self.confidence_threshold = 7
        self.min_rationale_length = 10


    """ 
        Accepts the assessment from the Prompt_processing_agent, and calls the method for evaluate the assessment
    """
    def process_request(self, input_request):
        assessment_text = input_request.get("assessment", "")
        result = self.evaluate_assessment(assessment_text)
        return {"text": result}

    """ 
        Evaluate the assessment from the Prompt_processing_agent based on its completeness and on the confidence level.
        It returns a message about incomplete assessment if there are missing or unknown fields.
        It prompts the Prompt_processing_agent to improve the assessment if the confidence level is below the threshold level. 
    """
    def evaluate_assessment(self, assessment_text):
        required_fields = ["Confidence:", "Confidence Rationale:", "Time to Act:"]
        missing_fields = [field for field in required_fields if field not in assessment_text]
        if missing_fields:
            return f"Incomplete response — missing fields: {', '.join(missing_fields)}."
        if "unknown" in assessment_text.lower():
            return "Response contains 'unknown'; consider providing more actionable assumptions."

        try:
            confidence_part = assessment_text.split("Confidence:")[-1].split()[0]
            score_str = confidence_part.split('/')[0]
            confidence_value = float(score_str)
            if confidence_value < self.confidence_threshold:
                return f"Confidence rating is too low ({confidence_value}/10); please improve the assessment with more detailed justification."
        except Exception:
            return "Could not parse confidence rating; please ensure it is in the correct format."

        try:
            rationale_part = assessment_text.split("Confidence Rationale:")[-1].splitlines()[0]
            if len(rationale_part.split()) < self.min_rationale_length:
                return "The confidence rationale is too brief; please provide a more detailed explanation for your confidence rating."
        except Exception:
            return "Could not parse confidence rationale; please ensure it is in the correct format."

        return "OK"
