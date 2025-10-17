#!/usr/bin/env python3
"""
Test script voor productie email configuratie
Verstuurt een test email via MailerSend
"""
import os
from services import email_service

def test_production_email():
    """Test productie email configuratie"""
    print("="*60)
    print("🧪 MailerSend Productie Test")
    print("="*60)
    
    if not email_service.enabled:
        print("❌ EmailService niet enabled - check MAILERSEND_API_KEY")
        return False
    
    print(f"\n✅ EmailService Status:")
    print(f"   From: {email_service.from_name} <{email_service.from_email}>")
    print(f"   API Key: {'✓ Present' if email_service.api_key else '✗ Missing'}")
    
    # Test email verzenden
    test_recipient = input("\n📧 Voer test email adres in (of Enter om over te slaan): ").strip()
    
    if not test_recipient:
        print("\n⏭️  Email test overgeslagen")
        return True
    
    print(f"\n📤 Verzenden test email naar {test_recipient}...")
    
    result = email_service.send_email(
        to_email=test_recipient,
        subject="🎉 Lexi CAO Meester - Productie Email Test",
        html_content=f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #1a2332;">Lexi CAO Meester - Email Test</h2>
            <p>Dit is een test email vanuit de productie omgeving.</p>
            <p><strong>Configuratie:</strong></p>
            <ul>
                <li>From: {email_service.from_name}</li>
                <li>Email: {email_service.from_email}</li>
                <li>MailerSend: Productie API Key</li>
            </ul>
            <p>Als je deze email ontvangt, werkt de MailerSend integratie correct! 🚀</p>
            <hr>
            <p style="color: #666; font-size: 12px;">
                Lexi AI - Jouw Expert CAO Assistent
            </p>
        </body>
        </html>
        """
    )
    
    if result:
        print("✅ Test email succesvol verzonden!")
        print(f"   Check {test_recipient} inbox (ook spam folder)")
        return True
    else:
        print("❌ Email verzenden mislukt - check logs voor details")
        return False

if __name__ == "__main__":
    test_production_email()
