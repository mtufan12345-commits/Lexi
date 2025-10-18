#!/usr/bin/env python3
"""
Test script voor uitnodigingsmail functionaliteit
"""

import os
import sys

# Setup environment
os.environ.setdefault('DATABASE_URL', os.getenv('DATABASE_URL'))
os.environ.setdefault('MAILERSEND_API_KEY', os.getenv('MAILERSEND_API_KEY'))

from services import EmailService

# Mock objects voor testen
class MockUser:
    def __init__(self):
        self.email = "test.user@example.com"
        self.first_name = "Jan"
        self.last_name = "de Vries"

class MockTenant:
    def __init__(self):
        self.company_name = "Test Uitzendbureau BV"
        self.subdomain = "testuitzendbureau"

def test_invitation_email():
    print("=" * 70)
    print(" " * 15 + "UITNODIGINGSMAIL TEST")
    print("=" * 70)
    print()
    
    # Initialiseer EmailService
    email_service = EmailService()
    
    if not email_service.enabled:
        print("⚠️  EmailService is niet actief (MAILERSEND_API_KEY niet ingesteld)")
        print("   Dit is OK voor development - de email wordt niet echt verzonden")
        print()
    else:
        print("✓ EmailService is actief en klaar om emails te versturen")
        print(f"  From: {email_service.from_email}")
        print(f"  Name: {email_service.from_name}")
        print()
    
    # Maak test objecten
    user = MockUser()
    tenant = MockTenant()
    login_url = f"https://{tenant.subdomain}.lex-cao.replit.app/login"
    password = "WelkomTest123!"
    admin_name = "Admin Gebruiker"
    
    print("Test parameters:")
    print(f"  Nieuwe gebruiker: {user.first_name} {user.last_name}")
    print(f"  Email: {user.email}")
    print(f"  Wachtwoord: {password}")
    print(f"  Bedrijf: {tenant.company_name}")
    print(f"  Uitgenodigd door: {admin_name}")
    print(f"  Login URL: {login_url}")
    print()
    
    # Test de email functie
    print("Verzenden uitnodigingsmail...")
    result = email_service.send_user_invitation_email(
        user=user,
        tenant=tenant,
        login_url=login_url,
        password=password,
        admin_name=admin_name
    )
    
    print()
    if result:
        print("✅ SUCCESS - Uitnodigingsmail verzonden!")
        print()
        print("De nieuwe gebruiker zou een email moeten ontvangen met:")
        print("  ✓ Welkomstboodschap")
        print("  ✓ Naam van de admin die hen uitnodigde")
        print("  ✓ Bedrijfsnaam")
        print("  ✓ Email adres voor login")
        print("  ✓ Wachtwoord (plain text)")
        print("  ✓ Login knop met directe link")
        print("  ✓ Lexi branding (navy blue en gold)")
        print("  ✓ Overzicht van Lexi features")
    else:
        if not email_service.enabled:
            print("ℹ️  Email niet verzonden (EmailService niet actief)")
            print("   In productie met MAILERSEND_API_KEY zou de email wel worden verzonden")
        else:
            print("❌ FAILED - Email kon niet worden verzonden")
            print("   Check de server logs voor meer details")
    
    print()
    print("=" * 70)
    print(" " * 20 + "TEST COMPLEET")
    print("=" * 70)

if __name__ == "__main__":
    test_invitation_email()
