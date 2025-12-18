# backend/chat/tools.py
from django.db import connection # To execute raw SQL
import json
import logging
import pandas as pd # For formatting SQL query results

logger = logging.getLogger(__name__)

def get_database_schema() -> str:
    """
    Dynamically fetches the schema for all user-defined tables in the connected database
    and returns it as a formatted Markdown string.
    This provides the LLM with the necessary context to generate SQL.
    """
    schema_info = []
    with connection.cursor() as cursor:
        # Get all table names from the current database
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;")
        table_names = [row[0] for row in cursor.fetchall()]

        for table_name in table_names:
            # Exclude internal Django tables if you don't want the LLM to query them
            if table_name.startswith('auth_') or \
               table_name.startswith('django_') or \
               table_name.startswith('admin_') or \
               table_name.startswith('sessions_'):
                continue

            # Get column details for each table
            cursor.execute(f"""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = '{table_name}'
                ORDER BY ordinal_position;
            """)
            columns = cursor.fetchall()
            
            column_details = []
            for col in columns:
                col_name, data_type, is_nullable, col_default = col
                column_details.append(f"- {col_name} ({data_type}, Nullable: {is_nullable}, Default: {col_default})")
            
            schema_info.append(f"### Table: `{table_name}`\n")
            schema_info.append(f"**Columns:**\n{'\n'.join(column_details)}\n")
            
            # Add example data for the table for better LLM understanding (optional, but highly recommended)
            try:
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 3;")
                example_rows = cursor.fetchall()
                example_columns = [desc[0] for desc in cursor.description]
                if example_rows:
                    example_data_str = "```\n" + " | ".join(example_columns) + "\n" + "-" * (sum(len(c) + 3 for c in example_columns) - 1) + "\n"
                    for row in example_rows:
                        example_data_str += " | ".join(map(str, row)) + "\n"
                    example_data_str += "```\n"
                    schema_info.append(f"**Sample Data:**\n{example_data_str}")
            except Exception as e:
                logger.warning(f"Could not fetch sample data for table {table_name}: {e}")
            
            schema_info.append("---\n") # Separator between tables

        return "\n".join(schema_info)


def execute_sql_query(sql_query: str) -> str:
    """
    Executes a SQL query against the database and returns results as a JSON string.
    DO NOT USE 'DROP TABLE', 'DELETE FROM', 'INSERT INTO', 'UPDATE', or other destructive queries.
    Only use SELECT queries.
    """
    logger.info(f"Attempting to execute SQL query: {sql_query}")
    try:
        # Basic validation to prevent destructive queries
        lower_query = sql_query.strip().lower()
        if not lower_query.startswith("select"):
            return json.dumps({"error": "Only SELECT queries are allowed for safety reasons. Do not generate INSERT, UPDATE, DELETE, or DROP statements."})
        
        # Additional safety check for common dangerous keywords
        forbidden_keywords = ['delete', 'drop', 'insert', 'update', 'alter', 'create', 'truncate']
        if any(keyword in lower_query for keyword in forbidden_keywords):
             return json.dumps({"error": "Generated SQL query contains forbidden keywords. Only SELECT queries are allowed."})


        with connection.cursor() as cursor:
            cursor.execute(sql_query)
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()

        # Convert to Pandas DataFrame for easy JSON serialization
        df = pd.DataFrame(rows, columns=columns)
        
        if df.empty:
            return json.dumps({"message": "No results found for the query."})
        
        # Limit to first 100 rows to prevent excessively large outputs for the LLM
        if len(df) > 100:
            df = df.head(100)
            logger.warning("SQL query returned more than 100 rows. Truncating for LLM.")
            # Indicate truncation to the LLM
            return json.dumps({"message": f"Query returned too many results, showing first {len(df)} rows. Data: " + df.to_json(orient='records')})
            
        return json.dumps(df.to_json(orient='records'))

    except Exception as e:
        logger.error(f"Error executing SQL query: {e}", exc_info=True)
        return json.dumps({"error": f"Failed to execute SQL query: {str(e)}. Please check query syntax or database accessibility."})

# --- Ollama Function Calling Schema (Tools Definition - kept for conceptual clarity, but not used in payload) ---
OLLAMA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_sql_query",
            "description": "Executes a SQL query against the EHS database. Use this to retrieve, count, or aggregate data. ONLY use SQL SELECT queries. Provide the full, valid SQL query as a string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql_query": {
                        "type": "string",
                        "description": "The complete SQL SELECT query to execute (e.g., 'SELECT COUNT(*) FROM safety_incident WHERE location = 'Warehouse A';'). Always include the 'FROM' clause with the table name."
                    }
                },
                "required": ["sql_query"]
            }
        }
    }
]

# Mapping of tool names to actual Python functions
AVAILABLE_TOOLS = {
    "execute_sql_query": execute_sql_query,
}
