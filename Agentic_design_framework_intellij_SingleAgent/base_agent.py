from google import genai
from abc import ABC, abstractmethod
import os
from dotenv import load_dotenv

class BaseAgent(ABC):
    def __init__(self, name, role, system_message, instructions, knowledge_base = None):
        load_dotenv()                                  # Load environment variables from a .env file
        self.name = name                               # Agent's name
        self.role = role                               # Agent's role
        self.system_message = system_message           # Parameter used for giving context to the agent and help it understand its role
        self.instructions = instructions               # Parameter used for giving instructions to the agent
        self.kb = knowledge_base                       # Predefined knowledge available for the agent to use
        self.status = "standby"                        # The current status of the agent
        self.temperature = 0.7                         # Parameter to control agent's creativity. Lower values mean less "creative" answers, thus, more deterministic answers. For more details visit https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/inference
        self.seed = 42                                 # Parameter to control agent's randomness in responses. For more details visit https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/inference
        self.model = "gemini-2.5-flash"                # Gemini LLM model. For more options visit https://ai.google.dev/gemini-api/docs/models
        
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("API Key is missing. Please set OPENAI_API_KEY in your environment.")


    """ Process incoming requests - must be implemented by each agent based on their role """
    @abstractmethod
    def process_request(self, input_request):
        pass

    """ Updates the status of the agent """
    def update_status(self, status):
        self.status = status
        return {"status": "updated", "new_status": status}

    """ Returns the status of the agent """
    def get_status(self):
        return self.status

    """ Calls the AI API and returns the response """
    def generate_response(self, prompt):
        client = genai.Client(api_key = self.api_key)
        response = client.models.generate_content(
            model = self.model,
            contents = prompt,
        )
        return {"text": response.text}