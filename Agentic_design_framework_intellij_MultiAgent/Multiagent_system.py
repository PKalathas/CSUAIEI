import traceback
import datetime
from Information_extraction_agent import Information_extraction_agent
from Prompt_processing_agent import Prompt_processing_agent
from Reflection_agent import Reflection_agent


"""
    A multi-agent class that uses three agents to analyze reports, extract medical information and assesses the urgency of each case.
"""
class Multiagent_system:
    def __init__(self, max_iterations=3):

        """
        Setting up the system messages and the instructions for each agent before they are instantiated
        """

        input_agent_system_message = ( "You are an expert in extracting key information from files.\n" 
                                       "Extract only the following details that are useful for a medical urgency assessment:\n"
                                       "1. Medical conditions or indications of health issues (e.g., diabetes, hypertension).\n"
                                       "2. A list of medications the missing person may be taking.\n"
                                       "3. The last dosage time for these medications if available." )

        input_agent_instructions = ( "Extract the following information from the file as a string:\n"
                                     "In the first line provide a list of medical conditions or any indications of health issues (e.g., diabetes, hypertension).\n"
                                     "in the next line provide a list of medications the missing person may be taking.\n"
                                     "in the last line provide the last dosage time for these medications, if available.\n"
                                     ""
                                     "Report Text:" )

        prompt_processing_agent_system_message = ( "You are a medical urgency assessment expert for search and rescue operations.\n"
                                                   "Assess urgency based on medical conditions, available medications, and time since the last dose.\n"
                                                   "If data is missing, make reasonable assumptions but indicate uncertainty where necessary.\n" )

        prompt_processing_agent_instructions =  ( "Please provide your assessment and any suggestions for missing medications.\n"
                                                  "On a new line, include your confidence rating in the format 'Confidence: X/10'.\n"
                                                  "On the next new line, provide a brief rationale for the confidence rating in the format 'Confidence Rationale: <explanation>'.\n"
                                                  "On the following new line, provide the maximum time to act (in hours) in the format 'Time to Act: X hours' with an explanation.\n"
                                                  "Finally, on a new line, state whether further iterations would significantly improve the assessment by answering 'Yes' or 'No'." )

        reflection_agent_system_message = ( "You are a search and rescue medical urgency assessment critic. Evaluate the provided medical urgency assessment for completeness, \n"
                                            "accuracy, and actionable recommendations. Ensure that the confidence rating is supported by a meaningful rationale." )

        reflection_agent_instructions = ( " Evaluate the provided medical urgency assessment for completeness, accuracy, and actionable recommendations.\n"
                                          " Ensure that the confidence rating is supported by a meaningful rationale.\n" )


        """
        Instantiates the agents and sets up the memory and the iterations of the system
        """

        self.input_agent = Information_extraction_agent(input_agent_system_message, input_agent_instructions)
        self.processing_agent = Prompt_processing_agent( prompt_processing_agent_system_message, prompt_processing_agent_instructions )
        self.reflection_agent = Reflection_agent( reflection_agent_system_message, reflection_agent_instructions )

        self.memory = []
        self.max_iterations = max_iterations


    """
        Synchronizes the agents to work with the given files and provide the medical urgency assessment.
        First, the input agent processes the input files and extracts the relevant information.
        The processing agent then creates the prompt and contacts th AI API.
        Then the reflection agents assesses the response, and based on the confidence level it tries to optimize it as much as possible
        using the given number of iterations.
    """

    def process_request(self, input_request):
        try:
            info_result = self.input_agent.process_request(input_request)
            tmp = info_result["text"].split("\n")
            patient_info = {
                "conditions": [c.strip() for c in tmp[0].split(",")],
                "medications": [m.strip() for m in tmp[1].split(",")],
                "last_dose_times": self.parse_last_dose_times(tmp[2])
            }

            current_prompt = self.processing_agent.create_prompt(patient_info)
            
            for iteration in range(1, self.max_iterations + 1):
                primary_msg = {
                    "prompt": current_prompt,
                    "iteration": iteration,
                    "patient_info": patient_info
                }
                primary_response = self.processing_agent.process_request(primary_msg)["text"]
                self.memory.append(f"Iteration {iteration}: {primary_response}")
                
                critique_msg = {"assessment": primary_response}
                critique = self.reflection_agent.process_request(critique_msg)["text"]
                
                if critique == "OK":
                    break
                else:
                    current_prompt = f"{primary_response}\nNote: Critic feedback - {critique}. Please refine the response."
            
            final_response = self.memory[-1]
            parsed_fields = self.processing_agent.parse_response_fields(final_response)
            formatted_output = self.processing_agent.format_output(parsed_fields, patient_info)
            
            unique_filename = self._generate_unique_filename(patient_info)
            with open(unique_filename, 'w', encoding='utf-8') as outfile:
                outfile.write(formatted_output)
            
            return formatted_output
        except Exception as e:
            tb = traceback.format_exc()
            return {"error": str(e), "traceback": tb}


    """
        Generates a unique file with the results
    """
    def _generate_unique_filename(self, patient_info):
        patient_id = patient_info.get("id")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if patient_id:
            filename = f"out_{timestamp}_{patient_id}.txt"
        else:
            filename = f"out_{timestamp}_unknown_patient.txt"
        return filename



    def parse_last_dose_times(self, last_dose_line):
        results = {}
        entries = last_dose_line.split(",")
        for entry in entries:
            if "~" in entry or "around" in entry:
                parts = entry.strip().replace("~", "around").split("around")
                med = parts[0].strip().rstrip(":")
                time_str = parts[1].strip()
                try:
                    now = datetime.datetime.now()
                    dose_time_obj = datetime.datetime.strptime(time_str, "%I:%M %p")
                    dose_datetime = now.replace(hour=dose_time_obj.hour, minute=dose_time_obj.minute, second=0, microsecond=0)
                    if dose_datetime > now:
                        dose_datetime -= datetime.timedelta(days=1)  
                    results[med] = dose_datetime.timestamp()
                except Exception as e:
                    print(f"Warning: Could not parse time for {med}: {e}")
        return results