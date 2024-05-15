import streamlit as st
import requests
from requests.exceptions import RequestException
from dotenv import load_dotenv
import os
import subprocess

# Load environment variables from .env file
load_dotenv()

# Run MindsDB setup
def run_mindsdb_setup():
    try:
        subprocess.run(["python", "setup_mindsdb.py"], check=True)
    except subprocess.CalledProcessError as e:
        st.error(f"Failed to setup MindsDB: {e}")

# Fetch environment variables
OLLAMA_HOST = os.getenv("OLLAMA_HOST")
OLLAMA_PORT = os.getenv("OLLAMA_PORT")
MINDSDB_HOST = os.getenv("MINDSDB_HOST")
MINDSDB_PORT = os.getenv("MINDSDB_PORT")
MINDSDB_API_KEY = os.getenv("MINDSDB_API_KEY")

# Sidebar settings
st.sidebar.header("Settings")

# API settings
st.sidebar.subheader("API Settings")
use_mindsdb = st.sidebar.checkbox("Use MindsDB", value=True)

ollama_host = st.sidebar.text_input("Ollama Host", value=OLLAMA_HOST)
ollama_port = st.sidebar.text_input("Ollama Port", value=OLLAMA_PORT)

def fetch_available_ollama_models(host, port):
    api_url = f"http://{host}:{port}/api/tags"
    try:
        response = requests.get(api_url)
        if response.status_code == 200:
            models = response.json().get('models', [])
            return [model['name'] for model in models]
        else:
            st.error(f"Failed to fetch Ollama models: {response.text}")
            return []
    except RequestException as e:
        st.error(f"An error occurred while fetching Ollama models: {e}")
        return []

ollama_models = fetch_available_ollama_models(ollama_host, ollama_port)
ollama_model = st.sidebar.selectbox("Ollama Model", ollama_models)

mindsdb_host = st.sidebar.text_input("MindsDB Host", value=MINDSDB_HOST)
mindsdb_port = st.sidebar.text_input("MindsDB Port", value=MINDSDB_PORT)
mindsdb_api_key = st.sidebar.text_input("MindsDB API Key", value=MINDSDB_API_KEY)

# Add username input
username = st.sidebar.text_input("Username", value="User")

# Initialize session state variables if they are not already initialized
if "use_mindsdb" not in st.session_state:
    st.session_state.use_mindsdb = use_mindsdb
if "ollama_host" not in st.session_state:
    st.session_state.ollama_host = ollama_host
if "ollama_port" not in st.session_state:
    st.session_state.ollama_port = ollama_port
if "ollama_model" not in st.session_state:
    st.session_state.ollama_model = ollama_model
if "mindsdb_host" not in st.session_state:
    st.session_state.mindsdb_host = mindsdb_host
if "mindsdb_port" not in st.session_state:
    st.session_state.mindsdb_port = mindsdb_port
if "mindsdb_api_key" not in st.session_state:
    st.session_state.mindsdb_api_key = mindsdb_api_key
if "username" not in st.session_state:
    st.session_state.username = username
if "messages" not in st.session_state:
    st.session_state.messages = []

# Add update button
if st.sidebar.button("Update Settings"):
    st.session_state.use_mindsdb = use_mindsdb
    st.session_state.ollama_host = ollama_host
    st.session_state.ollama_port = ollama_port
    st.session_state.ollama_model = ollama_model
    st.session_state.mindsdb_host = mindsdb_host
    st.session_state.mindsdb_port = mindsdb_port
    st.session_state.mindsdb_api_key = mindsdb_api_key
    st.session_state.username = username
    st.sidebar.success("Settings updated successfully.")
    run_mindsdb_setup()

OLLAMA_API_URL = f"http://{st.session_state.ollama_host}:{st.session_state.ollama_port}/api/v1/models/{st.session_state.ollama_model}/complete"
MINDSDB_API_URL = f"http://{st.session_state.mindsdb_host}:{st.session_state.mindsdb_port}/api/sql/query"
MINDSDB_HEADERS = {"Authorization": f"Bearer {st.session_state.mindsdb_api_key}"}

def send_message_to_mindsdb(message):
    query = f"SELECT response FROM ollama_model WHERE text = '{message}' AND username = '{st.session_state.username}'"
    data = {"query": query}
    try:
        response = requests.post(MINDSDB_API_URL, headers=MINDSDB_HEADERS, json=data)
        response.raise_for_status()  # Raise exception for non-200 status codes
        result = response.json()
        
        # Extract the clean response
        if "data" in result and isinstance(result["data"], list) and len(result["data"]) > 0 and isinstance(result["data"][0], list) and len(result["data"][0]) > 0:
            llm_response = result["data"][0][0]
        else:
            st.error("Unexpected response format from MindsDB.")
            llm_response = "Failed to get a valid response from MindsDB."
    except RequestException as e:
        st.error(f"Error communicating with MindsDB: {e}")
        llm_response = "Failed to communicate with MindsDB."
    return llm_response, "🤖"

def send_message_to_ollama(message):
    data = {
        "prompt": f"{message}\n\nUsername: {st.session_state.username}"
    }
    try:
        response = requests.post(OLLAMA_API_URL, json=data)
        response.raise_for_status()
        llm_response = response.json().get("choices")[0].get("text").strip()
    except RequestException as e:
        st.error(f"Error communicating with Ollama: {e}")
        llm_response = "Failed to communicate with Ollama."
    return llm_response, "🤖"

def send_message(message):
    if st.session_state.use_mindsdb:
        llm_response, bot_icon = send_message_to_mindsdb(message)
    else:
        llm_response, bot_icon = send_message_to_ollama(message)
    return llm_response, bot_icon

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Accept user input
if user_input := st.chat_input(f"{st.session_state.username}:"):
    st.session_state.messages.append({"role": st.session_state.username, "content": user_input})
    with st.chat_message(st.session_state.username):
        st.markdown(user_input)

    llm_response, bot_icon = send_message(user_input)

    st.session_state.messages.append({"role": bot_icon, "content": llm_response})
    with st.chat_message(bot_icon):
        st.markdown(llm_response)

st.sidebar.header("Application Info")
st.sidebar.info("This application interacts directly with a locally hosted LLM using either MindsDB or Ollama.")
