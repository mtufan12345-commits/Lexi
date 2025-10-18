#!/usr/bin/env python3
"""Test met simpele HTML template"""

import os
os.environ.setdefault('DATABASE_URL', os.getenv('DATABASE_URL'))
os.environ.setdefault('MAILERSEND_API_KEY', os.getenv('MAILERSEND_API_KEY'))

from services import EmailService

class MockUser:
    def __init__(self):
        self.email = "test.user@example.com"
        self.first_name = "Jan"
        self.last_name = "de Vries"

class MockTenant:
    def __init__(self):
        self.company_name = "Test Uitzendbureau BV"
        self.subdomain = "testuitzendbureau"

def test_simple_email():
    print("Testing simple email structure...")
    email_service = EmailService()
    
    user = MockUser()
    tenant = MockTenant()
    login_url = "https://testuitzendbureau.lex-cao.replit.app/login"
    
    # Test 1: Gebruik de werkende welcome email
    print("\n1. Testing send_welcome_email (should work)...")
    result1 = email_service.send_welcome_email(user, tenant, login_url)
    print(f"   Result: {'✓ Success' if result1 else '✗ Failed'}")
    
    # Test 2: Direct send_email met simpele HTML
    print("\n2. Testing direct send_email with simple HTML...")
    result2 = email_service.send_email(
        user.email,
        "Test Subject",
        "<html><body><p>Test email</p></body></html>"
    )
    print(f"   Result: {'✓ Success' if result2 else '✗ Failed'}")
    
    print("\nDone!")

if __name__ == "__main__":
    test_simple_email()
