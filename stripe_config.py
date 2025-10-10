# Stripe Price IDs Configuration
# These correspond to the products created in Stripe Dashboard

STRIPE_PRICES = {
    'starter': {
        'monthly': 'price_1SGiKZD8m8yYEAVBSAdF32kZ',
        'yearly': 'price_1SGiM5D8m8yYEAVB0ynuVjvl'
    },
    'professional': {
        'monthly': 'price_1SGiNlD8m8yYEAVBVtUAS1f4',
        'yearly': 'price_1SGiOrD8m8yYEAVBoAzWBMO9'
    },
    'enterprise': {
        'monthly': 'price_1SGiPXD8m8yYEAVBMSOSV5Dz',
        'yearly': 'price_1SGiQGD8m8yYEAVBQCSMOClc'
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
