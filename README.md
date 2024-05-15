## MindsDB and Ollama LLM Chat Application with Streamlit UI

### Overview

This project integrates MindsDB and Ollama with Streamlit to create an interactive chat application. Users can ask questions, and the application responds using a locally hosted language model. The project allows for customization and configuration through a user-friendly sidebar interface.

### Why MindsDB?

**MindsDB** is a powerful and flexible machine learning tool that simplifies the process of integrating machine learning models into applications. Here are some key reasons why MindsDB is used in this project:

1. **Ease of Integration**: MindsDB provides a simple API for integrating machine learning models, making it easy to connect to various data sources and applications.
2. **Model Management**: MindsDB allows for easy creation, management, and deployment of machine learning models. You can create models using a variety of engines and manage them centrally.
3. **Predictive Capabilities**: With MindsDB, you can run predictive queries directly against your models, making it straightforward to get real-time predictions and insights.
4. **Flexibility**: MindsDB supports multiple machine learning frameworks and engines, providing the flexibility to choose the best tools for your specific needs.
5. **Scalability**: MindsDB is designed to handle large-scale machine learning tasks, making it suitable for applications that require processing large datasets and real-time predictions.

By integrating MindsDB with Streamlit, this project leverages these benefits to create an interactive and customizable chat application that can be easily configured and extended.

### Features

- **Interactive Chat Interface**: Engage with the language model through a simple and intuitive chat interface.
- **Customizable Settings**: Configure MindsDB and Ollama settings directly from the sidebar.
- **Personalized Responses**: Enter your username to personalize interactions with the language model.
- **Session State Management**: Persist chat history and settings across reruns using Streamlit's session state.
- **Easy Setup**: Scripts provided to set up and configure MindsDB and Ollama seamlessly.

### Setup

1. **Clone the Repository**:
    ```sh
    git clone https://github.com/yourusername/streamlit-llm-chat.git
    cd streamlit-llm-chat
    ```

2. **Install Dependencies**:
    ```sh
    pip install -r requirements.txt
    ```

3. **Configure Environment Variables**:
    Create a `.env` file in the root directory with the following content:
    ```env
    MINDSDB_HOST=127.0.0.1
    MINDSDB_PORT=47334
    MINDSDB_API_KEY=your_mindsdb_api_key_here

    OLLAMA_HOST=127.0.0.1
    OLLAMA_PORT=11434
    ```

4. **Set Up MindsDB**:
    Run the setup script to configure MindsDB:
    ```sh
    python setup_mindsdb.py
    ```

5. **Run the Application**:
    Start the Streamlit application:
    ```sh
    streamlit run app.py
    ```

### Usage

- **Configure API Settings**: Use the sidebar to configure MindsDB and Ollama settings.
- **Enter Username**: Personalize your chat experience by entering your username in the sidebar.
- **Update Settings**: Click "Update Settings" in the sidebar to apply changes.
- **Interact with the Chat**: Type messages in the chat input field and receive responses from the language model.

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