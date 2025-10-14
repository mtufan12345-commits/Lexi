"""
Tenant Provisioning Service - Shared service for creating tenants from signup
Used by both Stripe webhook and signup_success fallback
"""
from datetime import datetime
from models import db, Tenant, User, Subscription, PendingSignup
try:
    from services.email_service import EmailService
except ImportError:
    EmailService = None  # Will be imported at runtime
import re


def get_max_users_for_tier(tier):
    """Get maximum users allowed for subscription tier"""
    tier_limits = {
        'starter': 5,
        'professional': 20,
        'enterprise': 999999
    }
    return tier_limits.get(tier, 5)


def provision_tenant_from_signup(pending_signup, stripe_session_data=None):
    """
    Idempotent tenant provisioning from PendingSignup record
    
    Args:
        pending_signup: PendingSignup model instance
        stripe_session_data: Optional Stripe checkout session data for additional validation
    
    Returns:
        tuple: (success: bool, user: User|None, error_msg: str|None)
    """
    email = pending_signup.email
    
    # IDEMPOTENCY: Check if user already exists
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        print(f"✓ User {email} already exists (tenant_id={existing_user.tenant_id}), skipping provisioning")
        
        # Cleanup pending signup
        try:
            db.session.delete(pending_signup)
            db.session.commit()
            print(f"✓ Cleaned up pending signup for {email}")
        except Exception as cleanup_error:
            print(f"⚠ Warning: Failed to cleanup pending signup: {cleanup_error}")
            db.session.rollback()
        
        return True, existing_user, None
    
    # Extract data from pending signup
    company_name = pending_signup.company_name
    contact_name = pending_signup.contact_name
    password_hash = pending_signup.password_hash  # Already hashed
    tier = pending_signup.tier
    billing = pending_signup.billing
    
    print(f"🔄 Provisioning tenant for: {email}, tier: {tier}, billing: {billing}")
    
    try:
        # Create unique subdomain
        base_subdomain = re.sub(r'[^a-z0-9]', '', company_name.lower().replace(' ', ''))[:20]
        subdomain = base_subdomain if base_subdomain else 'tenant'
        
        counter = 1
        original_subdomain = subdomain
        while Tenant.query.filter_by(subdomain=subdomain).first():
            subdomain = f"{original_subdomain}{counter}"
            counter += 1
        
        # Create tenant
        tenant = Tenant(
            company_name=company_name,
            subdomain=subdomain,
            contact_email=email,
            contact_name=contact_name,
            status='active',
            subscription_tier=tier,
            max_users=get_max_users_for_tier(tier)
        )
        db.session.add(tenant)
        db.session.flush()  # Get tenant.id
        
        # Create admin user
        name_parts = contact_name.split() if contact_name else []
        admin_user = User(
            tenant_id=tenant.id,
            email=email,
            first_name=name_parts[0] if name_parts else 'Admin',
            last_name=' '.join(name_parts[1:]) if len(name_parts) > 1 else '',
            role='admin',
            is_active=True,
            disclaimer_accepted_at=datetime.utcnow(),
            password_hash=password_hash
        )
        db.session.add(admin_user)
        
        # Create subscription with Stripe data if available
        stripe_customer_id = None
        stripe_subscription_id = None
        
        if stripe_session_data:
            stripe_customer_id = stripe_session_data.get('customer')
            stripe_subscription_id = stripe_session_data.get('subscription')
        
        subscription = Subscription(
            tenant_id=tenant.id,
            plan=tier,
            status='active',
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id
        )
        db.session.add(subscription)
        
        # Commit all changes
        db.session.commit()
        
        print(f"✅ Tenant provisioned successfully: {company_name} ({subdomain})")
        
        # Delete pending signup
        try:
            db.session.delete(pending_signup)
            db.session.commit()
            print(f"✓ Cleaned up pending signup for {email}")
        except Exception as cleanup_error:
            print(f"⚠ Warning: Failed to cleanup pending signup: {cleanup_error}")
            db.session.rollback()
        
        # Send welcome email (non-blocking)
        try:
            if EmailService:
                email_service = EmailService()
                login_url = f"https://{subdomain}.lex-cao.replit.app/login"
                email_service.send_welcome_email(admin_user, tenant, login_url)
                print(f"✓ Welcome email sent to {email}")
            else:
                print(f"⚠ EmailService not available - skipping welcome email")
        except Exception as email_error:
            print(f"⚠ Warning: Failed to send welcome email: {email_error}")
            # Don't fail provisioning if email fails
        
        return True, admin_user, None
        
    except Exception as e:
        db.session.rollback()
        error_msg = f"Failed to provision tenant: {str(e)}"
        print(f"❌ {error_msg}")
        return False, None, error_msg
