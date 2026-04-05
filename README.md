# Zoho Projects AI Assistant 🚀

A high-performance AI Chatbot and Full-Stack Dashboard seamlessly integrated with Zoho Projects. This application empowers teams to manage tasks, analyze resource utilization, and automate workload balancing natively through a conversational interface.

## ✨ Key Features & Capabilities

### 🤖 Intelligent AI Workflows:
- **Natural Language Parsing:** Replaces rigid UI syntax with intuitive command delegation.
- **Utilization-Based Auto-Assignment:** Dynamically analyzes active team workloads to automatically assign tasks to the member with the lowest active sprint load.
- **Self-Healing Data Sync:** Automatically manages and refreshes OAuth tokens for zero-downtime integration.
- **Dynamic UI Generation:** The AI dynamically renders JSON payloads into interactive, clickable UI buttons directly within the chat for guided context routing.

### 👤 User Workflow:
- **Conversational Management:** Interrogate and configure active Zoho Projects directly.
- **Seamless Integrations:** Create Tasks, Assign Users, Update Statuses, and Delete Items instantly.
- **Frictionless Auth:** Secure, One-Click OAuth setup directly from the application.

## 🏗️ High-Level Architecture

- **Frontend Dashboard (`frontend/`):** A responsive, Teams-inspired UI built with Vanilla JS, HTML, and CSS.
- **Backend Core (`main.py`):** The central nervous system powered by FastAPI. It handles Zoho OAuth2 handshakes, exposes robust REST endpoints, and manages the LLM orchestration pipeline.
- **External Integrations:** Communicates directly with Zoho's REST APIs, Groq Cloud, Hugging Face, and local Docker (Ollama) environments.

### 📂 Project Directory Structure
```text
zoho_ai/
 │
 ├── frontend/               (Vanilla JS Client-Side Dashboard)
 ├── main.py                 (Core FastAPI Server & LLM Fallback Orchestration)
 ├── start.sh                (One-Click Automated Deployment Script)
 ├── requirements.txt        (Python Dependencies)
 ├── .env                    (Secret Keys: Zoho, Groq, Portal IDs)
 └── zoho_tokens.json        (Persistent OAuth Cache - Auto-generated)
```

## ⚙️ Engineering Highlight: Multi-Tier LLM Fallback System

To guarantee near-zero downtime for natural language inference, the application features an advanced orchestration pipeline:

1. **Primary Intent Parser (Cloud - Groq):** Leverages `llama-3.3-70b-versatile` via Groq for lightning-fast intent recognition.
2. **First Fallback Tier (Local Container - Ollama):** If cloud rate limits are reached, traffic dynamically fails over to a local Dockerized `Ollama` node.
3. **Fail-Safe Disaster Recovery (Local CPU - Llama-CPP):** In the event of total network failure, the system executes an isolated, CPU-bound inference via Hugging Face (`Llama-3.2-3B-Instruct`).

*Models are governed by strict Python implementations of Zoho CRUD operations via Function Calling, ensuring absolute data security.*

## 🚀 Local Deployment Guide

### 1. Prerequisites
- **Python 3.9+**
- *(Optional)* Local `Ollama` running on port `11434`.

### 2. Environment Configuration
Create a `.env` file in the root directory:
```env
ZOHO_CLIENT_ID=your_client_id
ZOHO_CLIENT_SECRET=your_client_secret
ZOHO_REDIRECT_URI=http://localhost:8000/callback
PORTAL_ID=your_portal_id
GROQ_API_KEY=your_groq_api_key
```

### 3. One-Click Bootstrap Start (Mac/Linux)
A provided wrapper automates the environment setup.
```bash
chmod +x start.sh
./start.sh
```
*This script kills conflicting ports, initializes `.venv`, installs requirements, and launches FastAPI.*

### 4. Application Access
1. **Initial Setup:** Navigate to [http://localhost:8000/docs](http://localhost:8000/docs) and hit `/auth/login` to bind your Zoho Token.
2. **Dashboard:** Open [http://localhost:8000/app](http://localhost:8000/app) to chat!

---

## 🗂️ Branch Strategy

The repository follows a strict feature-branch workflow to maintain stability.

```text
main  (Production-ready core codebase)
 │
 ├── development  (Integration & staging tests)
 │    │
 │    ├── feature/* (Ephemeral logic upgrades)
 │    │
 │    └── bugfix/*  (Rapid UI tweaks or logic resolutions)
 │
 └── hotfix/*  (Emergency live patches)
```

---
