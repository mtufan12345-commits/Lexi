# Stripe Price IDs Configuration - PRODUCTION MODE
# These correspond to the products created in Stripe Dashboard (Live Mode)

STRIPE_PRICES = {
    'starter': {
        'monthly': 'price_1SGiKZD8m8yYEAVBSAdF32kZ',  # €499/maand
        'yearly': 'price_1SGiM5D8m8yYEAVB0ynuVjvl'    # Starter yearly
    },
    'professional': {
        'monthly': 'price_1SGiNlD8m8yYEAVBVtUAS1f4',  # €599/maand
        'yearly': 'price_1SGiOrD8m8yYEAVBoAzWBMO9'    # Professional yearly
    },
    'enterprise': {
        'monthly': 'price_1SGiPXD8m8yYEAVBMSOSV5Dz',  # €1.199/maand
        'yearly': 'price_1SGiQGD8m8yYEAVBQCSMOClc'    # Enterprise yearly
    }
}

# Helper function to get price ID
def get_price_id(tier, billing_cycle):
    """
    Get Stripe Price ID for a given tier and billing cycle
    
    Args:
        tier: 'starter', 'professional', or 'enterprise'
        billing_cycle: 'monthly' or 'yearly'
    
    Returns:
        Stripe Price ID or None if not found
    """
    return STRIPE_PRICES.get(tier, {}).get(billing_cycle)
