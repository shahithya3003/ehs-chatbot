# backend/chat/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import requests
import json
import logging 

# Import the tools functions (execute_sql_query, get_database_schema)
from .tools import AVAILABLE_TOOLS, get_database_schema

logger = logging.getLogger(__name__)

class ChatbotAPIView(APIView):
    def post(self, request, *args, **kwargs):
        user_message = request.data.get('message')
        if not user_message:
            return Response({"error": "No message provided."}, status=status.HTTP_400_BAD_REQUEST)

        ollama_response_text = "I'm sorry, I couldn't process that. Please try again."

        print(f"\n--- Chatbot Request Received: '{user_message}' ---")

        try:
            # Dynamically get the database schema
            # Ensure your PostgreSQL is running and settings.py is correct!
            dynamic_db_schema = get_database_schema()
            print(f"--- Dynamic DB Schema Generated ---\n{dynamic_db_schema}\n---------------------------------")


            # Phase 1: Call LLM to either get SQL or a direct conversational answer
            system_prompt_for_sql_or_direct = (
                "You are an expert EHS assistant. Your primary function is to help users query "
                "the EHS PostgreSQL database, or answer general EHS-related questions. "
                "When a user asks a question that requires data from the database, you MUST respond with ONLY the SQL query. "
                "Do NOT include any conversational text, explanations, or markdown formatting outside of the SQL query itself. "
                "The SQL query must be a valid SELECT statement for the `safety_incident` table based on the provided schema. "
                "Always include the 'FROM' clause. Use single quotes for string values.\n"
                "If the user's request cannot be fulfilled by a SQL query (e.g., 'Tell me a joke', 'Who are you?', 'Summarize a document'), "
                "respond conversationally without generating SQL.\n\n"
                "**Database Schema:**\n"
                f"{dynamic_db_schema}\n\n"
                "**Examples of SQL queries you might generate for 'safety_incident' table:**\n"
                "- To count all incidents: `SELECT COUNT(*) FROM safety_incident;`\n"
                "- To find incidents in Warehouse A: `SELECT * FROM safety_incident WHERE location = 'Warehouse A';`\n"
                "- To list high severity incidents: `SELECT id, type, date FROM safety_incident WHERE severity = 'High';`\n"
                "- To count incidents by type: `SELECT type, COUNT(*) FROM safety_incident GROUP BY type;`\n"
                "- To find incidents after a specific date: `SELECT * FROM safety_incident WHERE date > '2025-05-01';`\n"
                "Remember to only output SQL if it's a database query. Otherwise, respond naturally."
            )

            messages_for_first_ollama_call = [
                {"role": "system", "content": system_prompt_for_sql_or_direct},
                {"role": "user", "content": user_message}
            ]

            ollama_api_url = "http://127.0.0.1:11434/api/chat"
            
            ollama_payload_first = {
                "model": "phi3",
                "messages": messages_for_first_ollama_call,
                "stream": False
            }

            print(f"\n--- Sending First Request to Ollama (SQL Generation) ---")
            print(f"Payload:\n{json.dumps(ollama_payload_first, indent=2)}")
            first_ollama_raw_response = requests.post(ollama_api_url, json=ollama_payload_first, timeout=300)
            first_ollama_raw_response.raise_for_status()
            first_ollama_response_data = first_ollama_raw_response.json()
            print(f"\n--- Received First Response from Ollama ---")
            print(f"Response Data:\n{json.dumps(first_ollama_response_data, indent=2)}")

            llm_output_content = first_ollama_response_data.get("message", {}).get("content", "").strip()
            print(f"\nLLM's Raw Output: '{llm_output_content}'")

            # --- NEW SQL EXTRACTION LOGIC ---
            extracted_sql = None
            # Check if the output is a markdown code block for SQL
            if llm_output_content.startswith("```sql") and llm_output_content.endswith("```"):
                # Extract the SQL by removing the markdown code block delimiters
                extracted_sql = llm_output_content.replace("```sql", "").replace("```", "").strip()
                if not extracted_sql.lower().startswith("select"): # Double check if it's actually a SELECT
                     extracted_sql = None # If not select, treat as non-SQL
            
            # Fallback if not a markdown block but still starts with select (less common for Phi-3 with this prompt)
            if extracted_sql is None and llm_output_content.lower().startswith("select"):
                extracted_sql = llm_output_content # Use content directly if it starts with select but no markdown

            # --- END NEW SQL EXTRACTION LOGIC ---

            if extracted_sql: # Now check if SQL was successfully extracted
                # This is the block that will now run if SQL is detected
                print(f"--- LLM Generated SQL: {extracted_sql} ---") # Use extracted_sql here
                
                # Execute the SQL tool (defined in tools.py)
                tool_result_json_str = AVAILABLE_TOOLS["execute_sql_query"](sql_query=extracted_sql) # Pass extracted_sql
                
                # Parse the result string to a Python object/dict (it's JSON from tools.py)
                tool_result = json.loads(tool_result_json_str) 
                print(f"--- SQL Execution Result (JSON String): {tool_result_json_str} ---")

                # Phase 3: Send SQL results back to LLM for natural language summary
                messages_for_summary = messages_for_first_ollama_call + [
                    {"role": "assistant", "content": extracted_sql}, # LLM's SQL output, pass actual SQL
                    {"role": "user", "content": f"The following data was retrieved from the database based on the query: {tool_result_json_str}\n\nPlease summarize this information concisely and naturally for the user's original question: '{user_message}'. If the data contains an 'error' key, simply report that error to the user."}
                ]
                
                ollama_payload_summary = {
                    "model": "phi3",
                    "messages": messages_for_summary,
                    "stream": False
                }

                print(f"\n--- Sending Second Request to Ollama (Summary) ---")
                print(f"Payload:\n{json.dumps(ollama_payload_summary, indent=2)}")
                summary_ollama_raw_response = requests.post(ollama_api_url, json=ollama_payload_summary, timeout=300)
                summary_ollama_raw_response.raise_for_status()
                summary_ollama_response_data = summary_ollama_raw_response.json()
                print(f"\n--- Received Second Response from Ollama (Summary) ---")
                print(f"Response Data:\n{json.dumps(summary_ollama_response_data, indent=2)}")


                # Final response from LLM
                ollama_response_text = summary_ollama_response_data.get("message", {}).get("content", "Could not summarize SQL results.")
                print(f"\n--- Final LLM Summarized Response: '{ollama_response_text}' ---")

            else: # This block will now only run for non-SQL queries
                # LLM did not generate SQL, it's a direct conversational response
                print(f"--- LLM Provided Direct Conversational Response (No SQL Detected) ---")
                ollama_response_text = llm_output_content

        except requests.exceptions.ConnectionError:
            print("ERROR: ConnectionError: Could not connect to Ollama server. Please ensure Ollama is running.")
            ollama_response_text = "Sorry, I cannot connect to the AI service. Please ensure Ollama is running."
            return Response({"response": ollama_response_text}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except requests.exceptions.Timeout:
            print("ERROR: TimeoutError: Request to Ollama timed out. The AI model might be too large for your system or it's very busy.")
            ollama_response_text = "The AI service took too long to respond. Please try again or restart Ollama."
            return Response({"response": ollama_response_text}, status=status.HTTP_504_GATEWAY_TIMEOUT)
        except requests.exceptions.RequestException as e:
            error_details = e.response.text if e.response else str(e)
            print(f"ERROR: RequestException calling Ollama: {error_details}")
            ollama_response_text = f"An error occurred with the AI service: {error_details}. Please check Ollama logs."
            return Response({"response": ollama_response_text}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except json.JSONDecodeError as e:
            raw_response_text = first_ollama_raw_response.text if 'first_ollama_raw_response' in locals() else 'N/A'
            print(f"ERROR: JSONDecodeError: Ollama returned invalid JSON response: {e}. Raw response: {raw_response_text}")
            ollama_response_text = "Received an unreadable response from the AI service. Please check Ollama configuration."
            return Response({"response": ollama_response_text}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            import traceback
            print(f"CRITICAL ERROR: An unexpected error occurred in ChatbotAPIView: {e}")
            traceback.print_exc()
            ollama_response_text = "An unexpected server error occurred. Please contact support."
            return Response({"response": ollama_response_text}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"response": ollama_response_text}, status=status.HTTP_200_OK)

