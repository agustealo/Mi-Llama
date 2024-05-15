## Mi Llama: MindsDB and Ollama LLM Chat Application with Streamlit UI

### Overview

Mi Llama integrates MindsDB and Ollama with Streamlit to create an interactive chat application, similar to ChatGPT, but with enhanced customization and personalization capabilities. Users can ask questions, and the application responds using locally hosted language models. What sets Mi Llama apart is its ability for your AI models to improve their knowledge base on-the-fly using MindsDB, allowing for personalized responses and adaptation to specific use cases. The project includes a user-friendly sidebar interface for easy customization and configuration.

Mi Llama’s unique feature set makes it ideal for a variety of applications, such as dynamic customer support, personalized tutoring systems, and intelligent virtual assistants that learn and adapt over time. By leveraging the power of MindsDB, Mi Llama can seamlessly update its knowledge base with new information, making it particularly effective in environments where information frequently changes or requires constant updates.

### Technology Choices

| **MindsDB**                                                                                                       | **Ollama**                                                                                                     | **Streamlit**                                                                                                     |
| ---------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **Ease of Integration**: Simple API for integrating machine learning models, making it easy to connect to various data sources and applications. | **Customizable Models**: Models can be customized to suit specific application needs, enhancing user interaction quality. | **Integration**: Seamlessly integrates with Python libraries and tools, making it a natural choice for a Python-based project like Mi Llama. |
| **Model Management**: Easy creation, management, and deployment of machine learning models with a variety of engines managed centrally. | **Advanced Language Understanding**: Sophisticated language understanding, making the chat application more responsive and accurate. | **Real-Time Interactivity**: Supports real-time interactivity, enabling dynamic updates and user engagement. |
| **Predictive Capabilities**: Run predictive queries directly against models, making it straightforward to get real-time predictions and insights. | **Local Hosting**: Can be hosted locally, ensuring data privacy and security for sensitive information.       | **Ease of Use**: Designed to be easy for both developers and users, reducing development time and improving user experience. |
| **Flexibility**: Supports multiple machine learning frameworks and engines, providing the flexibility to choose the best tools for specific needs. | **Scalability**: Can handle large-scale language processing tasks, making it suitable for applications that require processing large amounts of text data. | **Rapid Development**: Intuitive API allows for quick creation of interactive applications. |

### Features

- **Interactive Chat Interface**: Engage with the language model through a simple and intuitive chat interface.
- **Customizable Settings**: Configure MindsDB and Ollama settings directly from the sidebar.
- **Personalized Responses**: Enter your username to personalize interactions with the language model.
- **Session State Management**: Persist chat history and settings across reruns using Streamlit's session state.
- **Easy Setup**: Scripts provided to set up and configure MindsDB and Ollama seamlessly.
- **Dynamic Knowledge Update**: On-the-fly enhancement of the AI models' knowledge base using MindsDB, providing up-to-date and relevant responses tailored to specific user needs.

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

### Future Enhancements

Mi Llama is continually evolving to provide even more powerful features and capabilities. Upcoming enhancements include:

- **File Embedding for Knowledge Update and Chat Session**: Seamlessly embed files to update the AI's knowledge base and enrich chat sessions.
- **SQL Connection/Communication CRUD**: Directly interact with SQL databases to perform create, read, update, and delete operations. Ask for predictions, calculations, and other data-driven Q&A on your database data, create, publish, or even edit data.
- **Web Options**: Enhanced functionalities such as web search, web scraping, and web interactions to provide more comprehensive responses.
- **Agents - CrewAI Capability**: Integrate AI agents capable of handling specific tasks and workflows, improving the overall user experience.

### Troubleshooting

- **Common Errors**:
    - `AttributeError`: Ensure all session state variables are initialized.
    - `RequestException`: Verify MindsDB and Ollama services are running and API settings are correct.
    - `CalledProcessError`: Check the output of the MindsDB setup script for details.

- **Debugging Tips**:
    - Use `st.write()` to output variables and responses for debugging.
    - Check console logs for additional error messages and stack traces.

### Tutorial
For a step-by-step guide on how I created Mi Llama, refer to the included tutorial [Mi Llama](Mi_Llama_TUTORIAL.md).

### Contributing

Contributions are welcome! Please feel free to submit issues, fork the repository, and create pull requests.

### License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.