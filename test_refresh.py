
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_FILE = "zoho_tokens.json"
ZOHO_ACCOUNTS_URL = os.getenv("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.in")
CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")

with open(TOKEN_FILE, "r") as f:
    tokens = json.load(f)

refresh_token = tokens.get("refresh_token")

print(f"Attempting refresh with CLIENT_ID: {CLIENT_ID[:5]}...")
response = requests.post(
    f"{ZOHO_ACCOUNTS_URL}/oauth/v2/token",
    data={
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
    },
    timeout=15,
)

print(f"Refresh Status: {response.status_code}")
print(f"Refresh Response: {response.text}")
