// Base JavaScript for all pages - CSP compliant (no eval, no Function constructor)

// Initialize dark mode from localStorage BEFORE page renders (prevents flash)
// This runs immediately, not waiting for DOMContentLoaded
(function() {
    if (localStorage.getItem('darkMode') === 'true' || (!localStorage.getItem('darkMode') && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        document.documentElement.classList.add('dark');
    }
})();

// SPA-like navigation without page reloads - SIMPLIFIED VERSION WITHOUT eval
function navigateTo(url) {
    // Fallback to regular navigation to avoid CSP issues
    // SPA navigation with dynamic script execution requires unsafe-eval
    window.location.href = url;
}

function initNavLinks() {
    document.querySelectorAll('a[href^="/"]').forEach(link => {
        // Skip external links, hash links, and already processed links
        if (link.hasAttribute('data-spa-nav') || 
            link.getAttribute('href').startsWith('#') ||
            link.getAttribute('target') === '_blank') {
            return;
        }
        
        link.setAttribute('data-spa-nav', 'true');
        link.addEventListener('click', (e) => {
            const href = link.getAttribute('href');
            
            // Don't intercept form submits, logout, or special routes
            if (href.includes('/logout') || 
                href.includes('/api/') ||
                href.includes('/chat') ||
                href.includes('/admin') ||
                href.includes('/super-admin')) {
                return; // Let it navigate normally
            }
            
            // For now, use regular navigation (CSP compliant)
            // e.preventDefault();
            // navigateTo(href);
        });
    });
}

// Handle browser back/forward
window.addEventListener('popstate', () => {
    location.reload();
});

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initNavLinks();
});
