import time
import Utilities
import traceback
from base_agent import BaseAgent


"""
    Agent for providing feedback on assignments
"""
class Feedback_agent(BaseAgent):
    def __init__(self):
        super().__init__(
            name = "Prompt_processing_agent",
            role = "Makes the call to the AI API",
            system_message = "You are a college professor with a senior level experience in Java programming.",
            instructions = ("The first line of the given file specifies the number of different Java files that are included in the current file."
                           "Each file starts with the line 'File:' and the number of the file."
                           "Go through the whole file and provide any feedback for improvement of the code.\n"
                           "Report Text:")
    )


    """ 
        Accepts the input file and calls the method to create the prompt.
        Then it calls the method to contact the AI API and generate the feedback from the LLM
    """
    def process_request(self, message):
        try:
            if "filepath" in message:
                report_text = Utilities.file_to_string(message["filepath"])     # Stores the file content into a string.
            else:
                report_text = message.get("report_text", "")

            prompt = self.create_prompt(report_text)                            # Creates a prompt from the file content.
            prompt_filename = str(time.localtime().tm_hour) + "_" + str(time.localtime().tm_min) + "_" + str(time.localtime().tm_sec) + "_" + message["filepath"].split(".")[0] + "_prompt.txt"

            with open(prompt_filename, 'w', encoding='utf-8') as outfile:
                outfile.write(prompt)

            response = self.generate_response(prompt)                           # Makes the API call and gets the response from the LLM.

            feedback_filename = str(time.localtime().tm_hour) + "_" + str(time.localtime().tm_min) + "_" + str(time.localtime().tm_sec) + "_" + "_feedback.txt"

            with open(feedback_filename, 'w', encoding='utf-8') as outfile:
                outfile.write(response["text"])


            return response["text"] #{"text": response.get("text", "")}

        except Exception as e:
            tb = traceback.format_exc()
            return {"error": str(e), "traceback": tb}


    """ 
        Creates the prompt by combining the system message, the instructions for the agent and the data from the input file
    """
    def create_prompt(self, report_text):
        prompt = ( self.system_message + self.instructions + f"{report_text}\n\n" )
        return prompt