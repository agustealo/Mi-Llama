import requests
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Fetch environment variables
MINDSDB_API_URL = f"http://{os.getenv('MINDSDB_HOST')}:{os.getenv('MINDSDB_PORT')}/api/sql/query"
MINDSDB_API_KEY = os.getenv("MINDSDB_API_KEY")

def setup_mindsdb():
    # Define the queries to setup MindsDB engine and model
    engine_creation_query = """
    DROP MODEL IF EXISTS ollama_model;
    DROP ML_ENGINE IF EXISTS ollama_engine;

    CREATE ML_ENGINE ollama_engine
    FROM ollama;

    CREATE MODEL ollama_model
    PREDICT response
    USING
        engine = 'ollama_engine',
        model_name = 'llama3',
        prompt_template = 'respond to {{text}} by {{username}}',
        ollama_serve_url = 'http://host.docker.internal:11434';
    """

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MINDSDB_API_KEY}"
    }

    data = {
        "query": engine_creation_query
    }

    try:
        response = requests.post(MINDSDB_API_URL, json=data, headers=headers)
        response.raise_for_status()  # Raise exception for non-200 status codes
        print("MindsDB setup completed successfully.")
    except requests.RequestException as e:
        print(f"An error occurred while setting up MindsDB: {e}")

if __name__ == "__main__":
    setup_mindsdb()
