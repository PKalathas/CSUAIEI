from Utilities import extract_text_from_pdf
from base_agent import BaseAgent

"""
    Extracts information from a given file based on the agent instructions
"""
class Information_extraction_agent(BaseAgent):
    def __init__(self, system_message, instructions):
        super().__init__(
            name = "Input_to_prompts_agent",
            role = "Converts input information to prompts",
            instructions = instructions,
            system_message = system_message
        )


    """
        Expects the input_request to contain either:
          - A 'report_text' key with the full missing person report text, or
          - A 'input_path' key pointing to the file to parse.
    """
    def process_request(self, input_request):
        if "pdf_path" in input_request:
            report_text = extract_text_from_pdf(input_request["pdf_path"])
        else:
            report_text = input_request.get("report_text", "")

        prompt = self.create_prompt(report_text)    # Creates the prompt by combining the system message, the instructions for the agent and the data from the input file
        response = self.generate_response(prompt)   # Makes the AI API call and extracts the information based on the agent's instructions
        return {"text": response.get("text", "")}


    """ 
        Creates the prompt by combining the system message, the instructions for the agent and the data from the input file
    """
    def create_prompt(self, report_text):
        prompt = ( self.system_message + self.instructions + f"{report_text}\n\n" )
        return prompt
