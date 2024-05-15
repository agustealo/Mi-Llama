### Tutorial: Creating the Mi Llama Chat Application with MindsDB, Ollama, and Streamlit

This tutorial will guide you through creating the Mi Llama chat application that leverages MindsDB and Ollama for interactive, customizable, and personalized responses using Streamlit for the user interface.

#### Prerequisites

- Basic knowledge of Python
- Python installed on your system
- Streamlit, MindsDB, and Ollama installed
- A MindsDB API key

### Step 1: Project Setup

1. **Create Project Directory**:
    Create a new directory for your project and navigate into it:
    ```sh
    mkdir mi-llama
    cd mi-llama
    ```

2. **Set Up Virtual Environment**:
    Create a virtual environment to manage your dependencies:
    ```sh
    python -m venv env
    source env/bin/activate  # On Windows use `env\Scripts\activate`
    ```

3. **Install Dependencies**:
    Create a `requirements.txt` file with the following content:
    ```plaintext
    streamlit
    requests
    python-dotenv
    ```

    Install the dependencies:
    ```sh
    pip install -r requirements.txt
    ```

4. **Environment Variables**:
    Create a `.env` file in the root directory with the following content:
    ```plaintext
    MINDSDB_HOST=127.0.0.1
    MINDSDB_PORT=47334
    MINDSDB_API_KEY=your_mindsdb_api_key_here

    OLLAMA_HOST=127.0.0.1
    OLLAMA_PORT=11434
    ```

### Step 2: Setting Up MindsDB

1. **Create the `setup_mindsdb.py` Script**:
    ```python
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
    ```

2. **Run the Setup Script**:
    Execute the setup script to configure MindsDB:
    ```sh
    python setup_mindsdb.py
    ```

### Step 3: Creating the Streamlit App

1. **Create the `app.py` Script**:
    ```python
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
            response = requests.post(OLLAMA

_API_URL, json=data)
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
    ```

### Step 4: Running the Application

To run the application, use the following command:
```sh
streamlit run app.py
```

### Step 5: Using the Application

1. **Configure API Settings**: Use the sidebar to configure MindsDB and Ollama settings.
2. **Enter Username**: Personalize your chat experience by entering your username in the sidebar.
3. **Update Settings**: Click "Update Settings" in the sidebar to apply changes.
4. **Interact with the Chat**: Type messages in the chat input field and receive responses from the language model.
5. **Embed Files for Knowledge Updates**: Use the sidebar to upload files that update the AI’s knowledge base.
6. **Perform SQL Operations**: Utilize the built-in SQL support for CRUD operations to manage your data.
7. **Web Interaction**: Leverage web scraping, searching, and interaction capabilities.
8. **Utilize Agents**: Deploy CrewAI agents for specialized tasks and enhanced AI capabilities.

### Advanced Customization

- **Customizing the MindsDB Model**: Modify `setup_mindsdb.py` to change the MindsDB model configuration.
- **Customizing the Ollama Model**: Update the `OLLAMA_API_URL` in `app.py` to change the Ollama model and prompt template.
- **Managing Session State**: Use Streamlit's session state to add new variables and manage existing ones.

### Troubleshooting

- **Common Errors**:
    - `AttributeError`: Ensure all session state variables are initialized.
    - `RequestException`: Verify MindsDB and Ollama services are running and API settings are correct.
    - `CalledProcessError`: Check the output of the MindsDB setup script for details.

- **Debugging Tips**:
    - Use `st.write()` to output variables and responses for debugging.
    - Check console logs for additional error messages and stack traces.

### Contributing

Contributions are welcome! Please feel free to submit issues, fork the repository, and create pull requests.

### License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.