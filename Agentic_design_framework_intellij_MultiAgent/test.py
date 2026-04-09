import time
from Multiagent_system import Multiagent_system

multisystem = Multiagent_system(max_iterations=3)    # Instantiates a multi-agent system

pdf_files = ["test1.pdf"]                                       # Input for the multi-agent system

for i, pdf in enumerate(pdf_files, start=1):                    # Loop for executing the multi-agent system
    print(f"\n=== ANALYZING PDF FILES: {pdf} ===")
    result = multisystem.process_request({"pdf_path": pdf})
    print(result)
    
    if i != len(pdf_files):                                     # Delays the execution of the next file due to API limitations. For more details on limitations visit https://ai.google.dev/gemini-api/docs/rate-limits
        time.sleep(1)