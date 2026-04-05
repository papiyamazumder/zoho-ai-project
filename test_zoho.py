
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_FILE = "zoho_tokens.json"
PORTAL_ID = os.getenv("PORTAL_ID")
ZOHO_DOMAIN = os.getenv("ZOHO_DOMAIN", "projectsapi.zoho.in")

with open(TOKEN_FILE, "r") as f:
    tokens = json.load(f)

access_token = tokens.get("access_token")
headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}

url = f"https://{ZOHO_DOMAIN}/restapi/portals/"
response = requests.get(url, headers=headers)

print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")
