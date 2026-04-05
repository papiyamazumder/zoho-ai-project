#!/bin/bash
# start.sh — One-click startup script for the Zoho Projects Assistant
# -------------------------------------------------------------------
# This script:
#   1. Kills any processes already running on the required ports
#   2. Creates (or reuses) a Python virtual environment
#   3. Installs all Python dependencies from requirements.txt
#   4. Starts the FastAPI backend on port 8000 (in the background)
#   5. Starts the Streamlit chat UI on port 8501 (in the foreground)
#
# Usage:  bash start.sh
# Access: Streamlit UI  → http://localhost:8501
#         FastAPI docs  → http://localhost:8000/docs
#         Task Hub UI   → http://localhost:8000/app

VENV_DIR=".venv"
PYTHON="python3"

echo "--- Zoho Projects Assistant ---"

# Step 1: Free up ports 8000 and 8501 if they are already in use
echo "[1/5] Clearing ports 8000 and 8501..."
lsof -ti:8000,8501 | xargs kill -9 2>/dev/null || true

# Step 2: Create a virtual environment if one does not already exist
if [ ! -d "$VENV_DIR" ]; then
    echo "[2/5] Creating Python virtual environment..."
    $PYTHON -m venv $VENV_DIR
else
    echo "[2/5] Virtual environment already exists — skipping creation."
fi

# Step 3: Activate the virtual environment
echo "[3/5] Activating virtual environment..."
source $VENV_DIR/bin/activate

# Step 4: Install or upgrade all dependencies listed in requirements.txt
echo "[4/5] Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

# Warn if the .env file is missing (the app needs API keys to run)
if [ ! -f ".env" ]; then
    echo ""
    echo "WARNING: .env file not found!"
    echo "Create a .env file with your ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET,"
    echo "ZOHO_REDIRECT_URI, PORTAL_ID, and GROQ_API_KEY before proceeding."
    echo ""
fi

# Step 5a: Start the FastAPI server in the background, log output to server.log
echo "[5/5] Starting FastAPI backend on http://localhost:8000 ..."
nohup uvicorn main:app --host 0.0.0.0 --port 8000 --reload > server.log 2>&1 &

# Wait briefly to let the FastAPI server initialise before Streamlit starts
sleep 2

# Step 5b: Start the Streamlit app in the foreground (keeps the terminal alive)
echo "[5/5] Starting Streamlit UI on http://localhost:8501 ..."
streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0

# This line is only reached if Streamlit exits
wait
