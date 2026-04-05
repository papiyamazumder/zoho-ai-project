#!/bin/bash
# start.sh — One-click startup script for the Zoho Projects Assistant
# -------------------------------------------------------------------
# This script:
#   1. Kills any processes already running on the required ports
#   2. Creates (or reuses) a Python virtual environment
#   3. Installs all Python dependencies from requirements.txt
#   4. Starts the FastAPI backend on port 8000
#
# Usage:  bash start.sh
# Access: FastAPI docs  → http://localhost:8000/docs
#         Task Hub UI   → http://localhost:8000/app

VENV_DIR=".venv"
PYTHON="python3"

echo "--- Zoho Projects Assistant ---"

# Step 1: Free up port 8000 if it is already in use
echo "[1/4] Clearing port 8000..."
lsof -ti:8000 | xargs kill -9 2>/dev/null || true

# Step 2: Create a virtual environment if one does not already exist
if [ ! -d "$VENV_DIR" ]; then
    echo "[2/4] Creating Python virtual environment..."
    $PYTHON -m venv $VENV_DIR
else
    echo "[2/4] Virtual environment already exists — skipping creation."
fi

# Step 3: Activate the virtual environment
echo "[3/4] Activating virtual environment..."
source $VENV_DIR/bin/activate

# Step 4: Install or upgrade all dependencies listed in requirements.txt
echo "[4/4] Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

# Warn if the .env file is missing (the app needs API keys to run)
if [ ! -f ".env" ]; then
    echo ""
    echo "WARNING: .env file not found!"
    echo "Create a .env file with your ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET,"
    echo "ZOHO_REDIRECT_URI, and PORTAL_ID before proceeding."
    echo ""
fi

# Step 5: Start the FastAPI server in the foreground
echo "[5/5] Starting FastAPI backend on http://localhost:8000 ..."
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
