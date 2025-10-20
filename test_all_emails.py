#!/usr/bin/env python3
"""
Test script voor alle email templates
Stuurt alle email types naar TEST_EMAIL_OVERRIDE address voor layout checking
"""
import os
os.environ['TEST_EMAIL_OVERRIDE'] = 'm_tufan123@live.nl'

from services import email_service
from models import Tenant, User, SupportTicket
from datetime import datetime

print("="*70)
print("📧 LEXI CAO MEESTER - EMAIL TEMPLATE TEST")
print("="*70)
print(f"Alle emails worden verzonden naar: {email_service.test_email_override}")
print("="*70)
print()

# Maak mock objecten voor testing
class MockTenant:
    def __init__(self):
        self.id = 1
        self.company_name = "TestBedrijf BV"
        self.contact_name = "Jan de Tester"
        self.contact_email = "admin@testbedrijf.nl"
        self.subdomain = "testbedrijf"

class MockUser:
    def __init__(self):
        self.id = 1
        self.email = "gebruiker@testbedrijf.nl"
        self.first_name = "Piet"
        self.last_name = "Tester"

class MockTicket:
    def __init__(self):
        self.id = 12345
        self.subject = "Help met CAO vraag"
        self.email = "support@testbedrijf.nl"

tenant = MockTenant()
user = MockUser()
ticket = MockTicket()

# Test emails
emails_to_send = [
    {
        "name": "1. Payment Success (Na succesvolle betaling)",
        "function": lambda: email_service.send_payment_success_email(tenant, "professional", 599)
    },
    {
        "name": "2. User Invitation (Nieuwe gebruiker uitgenodigd)",
        "function": lambda: email_service.send_user_invitation_email(
            user, tenant, "https://testbedrijf.lexiai.nl/login", "WelkomWachtwoord123!", "Jan de Tester"
        )
    },
    {
        "name": "3. Password Reset Link (Wachtwoord vergeten)",
        "function": lambda: email_service.send_password_reset_link_email(
            user, tenant, "https://testbedrijf.lexiai.nl/reset-password/abc123def456"
        )
    },
    {
        "name": "4. Payment Failed (Betaling mislukt)",
        "function": lambda: email_service.send_payment_failed_email(tenant)
    },
    {
        "name": "5. Trial Expiring - 7 dagen (Trial verloopt)",
        "function": lambda: email_service.send_trial_expiring_email(tenant, 7)
    },
    {
        "name": "6. Trial Expiring - 1 dag (Trial verloopt morgen)",
        "function": lambda: email_service.send_trial_expiring_email(tenant, 1)
    },
    {
        "name": "7. Subscription Updated (Plan gewijzigd)",
        "function": lambda: email_service.send_subscription_updated_email(tenant, "starter", "enterprise")
    },
    {
        "name": "8. Subscription Cancelled (Abonnement geannuleerd)",
        "function": lambda: email_service.send_subscription_cancelled_email(tenant)
    },
    {
        "name": "9. Role Changed (Gebruiker rol gewijzigd)",
        "function": lambda: email_service.send_role_changed_email(user, tenant, "TENANT_ADMIN", "Jan de Tester")
    },
    {
        "name": "10. Account Deactivated (Account gedeactiveerd)",
        "function": lambda: email_service.send_account_deactivated_email(user, tenant, "Jan de Tester")
    },
    {
        "name": "11. Ticket Resolved (Support ticket opgelost)",
        "function": lambda: email_service.send_ticket_resolved_email(ticket, tenant)
    }
]

# Verstuur alle test emails
success_count = 0
failed_count = 0

for idx, email_test in enumerate(emails_to_send, 1):
    print(f"\n[{idx}/{len(emails_to_send)}] Testing: {email_test['name']}")
    print("-" * 70)
    
    try:
        result = email_test['function']()
        if result:
            print(f"✅ SUCCESS")
            success_count += 1
        else:
            print(f"❌ FAILED")
            failed_count += 1
    except Exception as e:
        print(f"❌ ERROR: {e}")
        failed_count += 1
    
    # Kleine pauze tussen emails
    import time
    time.sleep(0.5)

print()
print("="*70)
print("📊 RESULTATEN")
print("="*70)
print(f"✅ Succesvol: {success_count}/{len(emails_to_send)}")
print(f"❌ Mislukt:   {failed_count}/{len(emails_to_send)}")
print()
print(f"📬 Check je inbox: {email_service.test_email_override}")
print("📁 Vergeet niet ook je spam folder te checken!")
print("="*70)
