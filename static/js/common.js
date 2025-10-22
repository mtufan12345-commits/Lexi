// Common JavaScript functions used across all pages - For CSP compliance

// Dark mode toggle
window.toggleDarkMode = function() {
    const html = document.documentElement;
    const isDark = html.classList.contains('dark');
    
    if (isDark) {
        html.classList.remove('dark');
        localStorage.setItem('darkMode', 'false');
    } else {
        html.classList.add('dark');
        localStorage.setItem('darkMode', 'true');
    }
}

// Mobile menu toggle
window.toggleMobileMenu = function() {
    const menu = document.getElementById('mobile-menu');
    if (menu) {
        menu.classList.toggle('hidden');
    }
}

// Initialize dark mode from localStorage on page load
document.addEventListener('DOMContentLoaded', function() {
    const darkMode = localStorage.getItem('darkMode');
    if (darkMode === 'true') {
        document.documentElement.classList.add('dark');
    }
});
