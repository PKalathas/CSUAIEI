import time
from Feedback_agent import Feedback_agent
from Utilities import file_to_string

#singlesystem = Singleagent_system( max_iterations=1 )                   # Instantiates a single-agent system
singlesystem = Feedback_agent()
java_files = [ "Main.java" ]                                      # Input for the single-agent system

java_code = "Number of files = " + str( len( java_files ) ) + "\n"
print( java_code )
for fileCount, code in enumerate( java_files, start=1 ):                  # Loop for executing the single-agent system
    java_code += "File: " + str( fileCount ) + "\n"
    java_code += file_to_string( code )     # Stores the file content into a string.
    print( fileCount )

prompt_filename = str(time.localtime().tm_hour) + "_" + str(time.localtime().tm_min) + "_" + str(time.localtime().tm_sec) + "_" + "_java_code.txt"

with open(prompt_filename, 'w', encoding='utf-8') as outfile:
    outfile.write(java_code)


print(f"\n=== ANALYZING JAVA FILES: {java_files} ===")
result = singlesystem.process_request({"filepath": java_files[0]})
print(result)