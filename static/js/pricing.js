// Pricing page JavaScript - All inline scripts moved to external file for CSP compliance

let isYearly = false;

const pricing = {
    monthly: {
        starter: '€499',
        professional: '€599',
        enterprise: '€1.199'
    },
    yearly: {
        starter: '€5.389',
        professional: '€6.469',
        enterprise: '€12.949'
    }
};

window.selectMonthly = function() {
    isYearly = false;
    const monthlyBtn = document.getElementById('monthly-btn');
    const yearlyBtn = document.getElementById('yearly-btn');
    
    // Update button styles
    monthlyBtn.classList.add('bg-gold-500', 'text-white');
    monthlyBtn.classList.remove('bg-gray-200', 'dark:bg-zinc-700', 'text-gray-700', 'dark:text-gray-300');
    
    yearlyBtn.classList.remove('bg-gold-500', 'text-white');
    yearlyBtn.classList.add('bg-gray-200', 'dark:bg-zinc-700', 'text-gray-700', 'dark:text-gray-300');
    
    // Update prices
    document.getElementById('price-starter').textContent = pricing.monthly.starter;
    document.getElementById('price-professional').textContent = pricing.monthly.professional;
    document.getElementById('price-enterprise').textContent = pricing.monthly.enterprise;
    
    document.getElementById('period-starter').textContent = '/maand';
    document.getElementById('period-professional').textContent = '/maand';
    document.getElementById('period-enterprise').textContent = '/maand';
}

window.selectYearly = function() {
    isYearly = true;
    const monthlyBtn = document.getElementById('monthly-btn');
    const yearlyBtn = document.getElementById('yearly-btn');
    
    // Update button styles
    yearlyBtn.classList.add('bg-gold-500', 'text-white');
    yearlyBtn.classList.remove('bg-gray-200', 'dark:bg-zinc-700', 'text-gray-700', 'dark:text-gray-300');
    
    monthlyBtn.classList.remove('bg-gold-500', 'text-white');
    monthlyBtn.classList.add('bg-gray-200', 'dark:bg-zinc-700', 'text-gray-700', 'dark:text-gray-300');
    
    // Update prices
    document.getElementById('price-starter').textContent = pricing.yearly.starter;
    document.getElementById('price-professional').textContent = pricing.yearly.professional;
    document.getElementById('price-enterprise').textContent = pricing.yearly.enterprise;
    
    document.getElementById('period-starter').textContent = '/jaar';
    document.getElementById('period-professional').textContent = '/jaar';
    document.getElementById('period-enterprise').textContent = '/jaar';
}

// Signup function with billing cycle
window.startSignup = function(tier) {
    const billingCycle = isYearly ? 'yearly' : 'monthly';
    window.location.href = `/signup/tenant?tier=${tier}&billing=${billingCycle}`;
}

// Initialize - monthly is already active in HTML
