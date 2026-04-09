1. Get a Gemini API key from https://aistudio.google.com/app/apikey?_gl=1*1a8kfv9*_ga*MTM5NDcxMTkxMy4xNzQwOTc3ODU1*_ga_P1DBVKWT6V*MTc0NTcwNzgwMi41LjAuMTc0NTcwNzgwMi42MC4wLjE2MTg2MTk5NzU.
and paste it in the .env file as the value of "OPENAI_API_KEY"

2. Run the test.py file. It will execute examples for both the multiagent and the singleagent systems. If you want to run them separately, comment out the first
loop to run only the singleagent system or the second loop to run only the multiagent system

Note: If you have problems with google and genai open the console and try installing them with "pip install google-generativeai" and "pip install google-genai" without the quotes.

