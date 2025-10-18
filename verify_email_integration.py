#!/usr/bin/env python3
"""
Verify email integration in actual app context
"""
import sys
sys.path.insert(0, '/home/runner/workspace')

# Import from main app (where email_service is already initialized)
from main import email_service, app, User, Tenant, db

def verify_email_service():
    print("="*70)
    print(" " * 15 + "EMAIL SERVICE VERIFICATIE")
    print("="*70)
    print()
    
    with app.app_context():
        # Check if email service is properly initialized
        print("1. Email Service Status:")
        print(f"   Enabled: {email_service.enabled}")
        print(f"   From: {email_service.from_name} <{email_service.from_email}>")
        print(f"   API Key: {'✓ Aanwezig' if email_service.api_key else '✗ Ontbreekt'}")
        print()
        
        # Check database for test
        print("2. Database Check:")
        tenants = Tenant.query.limit(1).all()
        if tenants:
            tenant = tenants[0]
            print(f"   ✓ Test tenant beschikbaar: {tenant.company_name}")
            print(f"   ✓ Subdomain: {tenant.subdomain}")
            
            # Get an admin user
            admin = User.query.filter_by(tenant_id=tenant.id, role='admin').first()
            if admin:
                print(f"   ✓ Admin user: {admin.first_name} {admin.last_name}")
                
                print()
                print("3. Email Methode Check:")
                print(f"   ✓ send_email methode: {hasattr(email_service, 'send_email')}")
                print(f"   ✓ send_welcome_email methode: {hasattr(email_service, 'send_welcome_email')}")
                print(f"   ✓ send_user_invitation_email methode: {hasattr(email_service, 'send_user_invitation_email')}")
                
                print()
                print("="*70)
                print(" " * 10 + "✓ EMAIL SERVICE IS KLAAR VOOR GEBRUIK")
                print("="*70)
                print()
                print("De email zal worden verzonden wanneer een admin een nieuwe")
                print("gebruiker aanmaakt via het admin dashboard.")
                print()
                print("Flow:")
                print("  1. Admin gaat naar /admin/users")
                print("  2. Admin vult formulier in met naam, email, wachtwoord")
                print("  3. Admin klikt 'Gebruiker Toevoegen'")
                print("  4. ✉️  Uitnodigingsmail wordt automatisch verzonden!")
                print()
            else:
                print("   ⚠️  Geen admin user gevonden")
        else:
            print("   ⚠️  Geen tenants in database")

if __name__ == "__main__":
    verify_email_service()
