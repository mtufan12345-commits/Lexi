#!/usr/bin/env python3
"""Test nieuwe HTTP-based email implementation"""

import os
import sys

os.environ.setdefault('DATABASE_URL', os.getenv('DATABASE_URL'))
os.environ.setdefault('MAILERSEND_API_KEY', os.getenv('MAILERSEND_API_KEY'))

from services import EmailService

def test_http_email():
    print("=" * 70)
    print(" " * 15 + "HTTP EMAIL IMPLEMENTATION TEST")
    print("=" * 70)
    print()
    
    email_service = EmailService()
    
    print("1. EmailService Status:")
    print(f"   Enabled: {email_service.enabled}")
    print(f"   From: {email_service.from_name} <{email_service.from_email}>")
    print(f"   API URL: {email_service.api_url}")
    print(f"   API Key: {'✓ Present' if email_service.api_key else '✗ Missing'}")
    print()
    
    if not email_service.enabled:
        print("⚠️  EmailService disabled - no API key")
        return False
    
    # Test simple email
    print("2. Testing simple email send...")
    result = email_service.send_email(
        to_email="test@example.com",
        subject="Test Email",
        html_content="<html><body><p>Test email via HTTP</p></body></html>"
    )
    
    print()
    if result:
        print("✅ SUCCESS - HTTP email implementation works!")
    else:
        print("❌ FAILED - Check logs for details")
    
    print()
    print("=" * 70)
    return result

if __name__ == "__main__":
    test_http_email()
