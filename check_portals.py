
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_FILE = "zoho_tokens.json"
ZOHO_DOMAIN = os.getenv("ZOHO_DOMAIN", "projectsapi.zoho.in")

def get_headers():
    with open(TOKEN_FILE, "r") as f:
        tokens = json.load(f)
    return {"Authorization": f"Zoho-oauthtoken {tokens.get('access_token')}"}

try:
    url = f"https://{ZOHO_DOMAIN}/restapi/portals/"
    response = requests.get(url, headers=get_headers())
    print(f"Portals Status: {response.status_code}")
    portals = response.json().get("portals", [])
    if portals:
        for p in portals:
            print(f"Found Portal: {p.get('name')} (ID: {p.get('id')})")
    else:
        print("No portals found or error in response.")
except Exception as e:
    print(f"Error: {e}")
