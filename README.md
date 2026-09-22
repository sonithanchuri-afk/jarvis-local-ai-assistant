# JARVIS — Local AI Voice Assistant

> A futuristic personal AI assistant running locally with Python, Ollama, and Llama 3.

JARVIS is a personal AI assistant designed to provide a conversational, voice-enabled interface for interacting with a local large language model.

The project combines **Python**, **Ollama**, **Llama 3**, **CustomTkinter**, **speech recognition**, and **text-to-speech** to create a futuristic desktop assistant inspired by AI assistants such as JARVIS from the Iron Man universe.

The goal of this project is to learn how modern AI assistants work while keeping the core AI processing local and avoiding the need for a paid cloud AI API.

---

## Features

* 🧠 Local AI responses using Ollama
* 🤖 Llama 3 language model
* 🎤 Speech-to-text input
* 🔊 Text-to-speech responses
* 🖥️ Futuristic CustomTkinter interface
* 💬 Conversational chat interface
* 🔵 Animated JARVIS-style interface
* 📡 Online / Listening / Thinking / Speaking status indicators
* ⚡ Local processing without requiring a paid AI API
* 🐍 Built entirely with Python

---

## Architecture

```text
                 ┌──────────────────────┐
                 │       USER           │
                 │  Voice / Text Input  │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │    JARVIS UI        │
                 │    CustomTkinter     │
                 └──────────┬───────────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
     ┌─────────────────┐        ┌─────────────────┐
     │ SpeechRecognition│        │   Text Input    │
     └────────┬────────┘        └────────┬────────┘
              │                          │
              └────────────┬─────────────┘
                           ▼
                  ┌──────────────────┐
                  │      Ollama      │
                  │   Local LLM API  │
                  └────────┬─────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │     Llama 3      │
                  │   Local Model    │
                  └────────┬─────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │    JARVIS UI     │
                  └────────┬─────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │   pyttsx3 TTS    │
                  │   Voice Output   │
                  └──────────────────┘
```

---

## Tech Stack

| Technology        | Purpose                     |
| ----------------- | --------------------------- |
| Python            | Main programming language   |
| Ollama            | Local AI model runtime      |
| Llama 3           | Large language model        |
| CustomTkinter     | Desktop graphical interface |
| SpeechRecognition | Speech-to-text              |
| pyttsx3           | Text-to-speech              |
| Threading         | Keeping the UI responsive   |

---

## Project Structure

```text
jarvis-local-ai-assistant/
│
├── jarvis.py
├── jarvis_voice.py
├── jarvis_ui.py
├── brain.py
├── requirements.txt
├── README.md
├── .gitignore
└── assets/
    └── screenshots/
```

> The exact file structure may be updated to match the current project files.

---

## Requirements

Before running JARVIS, install:

* Python 3.10+
* Ollama
* Llama 3
* A working microphone
* Speakers or headphones

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR-USERNAME/jarvis-local-ai-assistant.git
cd jarvis-local-ai-assistant
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it on Windows:

```powershell
.venv\Scripts\Activate.ps1
```

### 3. Install Python dependencies

```bash
python -m pip install -r requirements.txt
```

If `requirements.txt` does not exist yet, install the required packages:

```bash
python -m pip install ollama customtkinter SpeechRecognition pyttsx3
```

---

## Ollama Setup

Install Ollama and download the Llama 3 model.

```bash
ollama pull llama3
```

Check that the model is available:

```bash
ollama list
```

You should see:

```text
llama3
```

Make sure Ollama is running before starting JARVIS.

---

## Running JARVIS

Run the main interface:

```bash
python jarvis_ui.py
```

The application should open the JARVIS desktop interface.

You can then:

1. Type a message.
2. Press the voice button.
3. Speak to JARVIS.
4. JARVIS converts your speech to text.
5. Ollama sends the prompt to Llama 3.
6. The response appears in the interface.
7. JARVIS can speak the response using text-to-speech.

---

## Example

```text
USER:
What is artificial intelligence?

JARVIS:
Artificial intelligence is the field of computer science focused
on creating systems that can perform tasks that normally require
human intelligence...
```

---

## Why Local AI?

One of the main goals of this project is to experiment with AI without depending entirely on cloud APIs.

With Ollama, the language model runs locally on the computer.

This provides:

* Local model execution
* No per-request API cost
* Greater control over the application
* An excellent environment for learning AI development

Performance will depend on the computer's hardware and the model being used.

---

## Learning Goals

This project was created as a hands-on way to learn:

* Python application development
* GUI development
* Local LLMs
* Ollama
* Prompt engineering
* Speech recognition
* Text-to-speech
* Multithreading
* AI application architecture
* Retrieval-Augmented Generation (RAG)

---

## Future Plans

The project is intended to grow beyond a simple chatbot.

Planned improvements include:

* [ ] RAG document knowledge
* [ ] Persistent conversation memory
* [ ] File understanding
* [ ] PDF/document question answering
* [ ] Web search capabilities
* [ ] Tool calling
* [ ] Computer automation
* [ ] Custom wake-word detection
* [ ] Improved voice recognition
* [ ] Multiple local models
* [ ] Better conversation history
* [ ] Plugin/tool architecture
* [ ] More advanced JARVIS-style UI

---

## Security

Never store API keys, passwords, tokens, personal credentials, or other secrets directly in the repository.

Use environment variables or local configuration files instead.

Make sure files containing secrets are included in `.gitignore`.

---

## Disclaimer

JARVIS is an educational personal AI assistant project.

The name and interface are inspired by fictional AI assistants and are not affiliated with Marvel, Disney, or any other related rights holder.

---

## Author

Built as a personal AI and Python learning project.

**Author:** YOUR-NAME

---

## License

This project is licensed under the MIT License.

See `LICENSE` for details.
