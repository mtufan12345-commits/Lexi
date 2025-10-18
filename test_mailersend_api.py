#!/usr/bin/env python3
"""Direct test van MailerSend API key"""

import os
import requests

api_key = os.getenv('MAILERSEND_API_KEY')

if not api_key:
    print("❌ MAILERSEND_API_KEY niet gevonden")
    exit(1)

print("Testing MailerSend API...")
print(f"API Key aanwezig: {len(api_key)} characters")
print(f"Starts with: {api_key[:10]}...")
print()

# Test API key door account info op te halen
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# Try to get account info (simpler endpoint)
print("Testing authentication met /v1/analytics/date endpoint...")
response = requests.get(
    "https://api.mailersend.com/v1/analytics/date",
    headers=headers,
    params={"date_from": "2025-01-01", "date_to": "2025-01-02"}
)

print(f"Status: {response.status_code}")
print(f"Response: {response.text[:200]}")
print()

if response.status_code == 401:
    print("❌ API key is NIET geldig of verlopen")
    print("   → Check je MailerSend dashboard voor een nieuwe API key")
elif response.status_code in [200, 422]:  # 422 = validation error but auth worked
    print("✅ API key is GELDIG - authenticatie werkt!")
else:
    print(f"⚠️  Unexpected status: {response.status_code}")

