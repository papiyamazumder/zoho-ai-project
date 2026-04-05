#!/bin/bash

# Configuration
VENV_DIR=".venv"
PYTHON="python3"

echo "🚀 Starting Zoho Assistant Setup..."

# 1. Create Virtual Environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating virtual environment..."
    $PYTHON -m venv $VENV_DIR
fi

# 2. Activate Virtual Environment
source $VENV_DIR/bin/activate

# 3. Install/Update dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 4. Check for .env file
if [ ! -f ".env" ]; then
    echo "⚠️  WARNING: .env file not found! Please create one using the provided instructions."
fi

# 5. Start the FastAPI server
echo "⚡ Starting the server on http://localhost:8000"
echo "👉 Once running, visit http://localhost:8000/auth/login to connect Zoho."
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
