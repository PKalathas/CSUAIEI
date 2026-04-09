import time
from base_agent import BaseAgent

"""
    Agent for assessing the medical urgency based on given information about the missing person
"""
class Prompt_processing_agent(BaseAgent):
    def __init__(self, system_message, instructions):
        super().__init__(
            name = "Prompt_processing_agent",
            role = "Makes the call to the AI API",
            system_message = system_message,
            instructions = instructions
        )


    """
        Accepts the patient information, calls the method to generate the prompt for the AI API and finally call the method to generate the assessment
    """
    def process_request(self, input_request):
        iteration = input_request.get("iteration", 1)
        prompt = input_request.get("prompt")
        if not prompt:
            patient_info = input_request.get("patient_info", {})
            prompt = self.create_prompt(patient_info)
        response_text = self.generate_assessment(prompt, iteration)
        return {"text": response_text}


    """ 
        Creates the prompt by combining the system message, the instructions for the agent and the data from the patient info
    """
    def create_prompt(self, patient_info):
        conditions = patient_info.get("conditions", [])
        medications = patient_info.get("medications", [])
        last_dose_times = patient_info.get("last_dose_times", {})

        conditions_text = ", ".join(conditions) if conditions else "unknown conditions"
        medications_text = ", ".join(medications) if medications else "unknown (no list provided)"

        if last_dose_times:
            last_dose_text = "\n".join(
                f"- {condition}: {round((time.time() - dose_time) / 3600, 1)} hours ago"
                for condition, dose_time in last_dose_times.items()
            )
        else:
            last_dose_text = "Unknown last dose times. Assume standard medication schedules."

        return (
            f"A person is missing with the following medical conditions: {conditions_text}. "
            f"They regularly take these medications: {medications_text}. "
            f"Their last recorded doses were:\n{last_dose_text}\n"
            "Please evaluate the situation."
        )


    """ 
        Calls the AI API and generates the medical urgency assessment
    """
    def generate_assessment(self, prompt, iteration):
        combined_prompt = (
            f"{self.system_message}\n"
            f"{prompt}\n"
            f"Iteration {iteration}:\n"
             + self.instructions
        )
        response = self.generate_response(combined_prompt)
        return response.get("text", "")


    """
        Expects the final response to have the following structure (last four non-empty lines):
         - Confidence: X/10
         - Confidence Rationale: <explanation>
         - Time to Act: X hours (with explanation)
         - Continue: Yes/No
        Everything preceding these four lines is the assessment summary.
    """
    def parse_response_fields(self, text):
        lines = text.strip().splitlines()
        non_empty_lines = [line.strip() for line in lines if line.strip()]
        if len(non_empty_lines) < 4:
            return {
                "assessment_summary": text,
                "confidence": None,
                "confidence_rationale": None,
                "time_to_act": None,
                "continue": "No"
            }
        confidence_line = non_empty_lines[-4]
        rationale_line = non_empty_lines[-3]
        time_to_act_line = non_empty_lines[-2]
        continue_line = non_empty_lines[-1]
        assessment_summary = "\n".join(non_empty_lines[:-4])
        confidence = confidence_line.split("Confidence:")[-1].strip() if "Confidence:" in confidence_line else None
        confidence_rationale = rationale_line.split("Confidence Rationale:")[-1].strip() if "Confidence Rationale:" in rationale_line else None
        time_to_act = time_to_act_line.split("Time to Act:")[-1].strip() if "Time to Act:" in time_to_act_line else None

        return {
            "assessment_summary": assessment_summary,
            "confidence": confidence,
            "confidence_rationale": confidence_rationale,
            "time_to_act": time_to_act,
            "continue": continue_line
        }


    """
        Formats the information for writing to an output file
    """
    def format_output(self, parsed_fields, patient_info):
        conditions = patient_info.get("conditions", [])
        medications = patient_info.get("medications", [])
        last_dose_times = patient_info.get("last_dose_times", {})

        conditions_text = ", ".join(conditions) if conditions else "None"
        medications_text = ", ".join(medications) if medications else "None"
        if last_dose_times:
            dose_times_text = "\n".join(
                f"- {med}: {round((time.time() - ts) / 3600, 1)} hours ago"
                for med, ts in last_dose_times.items()
            )
        else:
            dose_times_text = "No last dose times available."

        return (
            f"--- Input Data ---\n"
            f"Medical Conditions: {conditions_text}\n"
            f"Medications: {medications_text}\n"
            f"Last Dose Times:\n{dose_times_text}\n\n"
            f"--- Medical Urgency Assessment ---\n\n"
            f"Assessment Summary:\n{parsed_fields.get('assessment_summary', 'N/A')}\n\n"
            f"Confidence: {parsed_fields.get('confidence', 'N/A')}\n"
            f"Confidence Rationale: {parsed_fields.get('confidence_rationale', 'N/A')}\n"
            f"Time to Act: {parsed_fields.get('time_to_act', 'N/A')}\n"
            f"Further Iterations Needed: {parsed_fields.get('continue', 'N/A')}\n\n"
            f"-------------------------------------"
        )