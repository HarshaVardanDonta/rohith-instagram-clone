// Authentication utilities

// Check if user is authenticated
function checkAuth() {
    // Look for auth cookies - we can't access httpOnly cookies from JS
    // but we can check if the body has an auth class
    // This will be set by the server when rendering templates
    
    return document.body.classList.contains('is-authenticated');
}

// Initialize auth state
function initAuth() {
    const isAuthenticated = checkAuth();
    
    // Show/hide auth-dependent elements
    if (isAuthenticated) {
        document.querySelectorAll('.auth-required').forEach(el => {
            el.style.display = 'block';
        });
        
        document.querySelectorAll('.auth-hidden').forEach(el => {
            el.style.display = 'none';
        });
    } else {
        document.querySelectorAll('.auth-required').forEach(el => {
            el.style.display = 'none';
        });
        
        document.querySelectorAll('.auth-hidden').forEach(el => {
            el.style.display = 'block';
        });
    }
    
    // Setup user dropdown menu
    const userMenu = document.querySelector('.user-menu');
    if (userMenu) {
        const userAvatar = userMenu.querySelector('.user-avatar');
        
        if (userAvatar) {
            userAvatar.addEventListener('click', function(e) {
                e.preventDefault();
                userMenu.classList.toggle('open');
            });
            
            // Close dropdown when clicking outside
            document.addEventListener('click', function(e) {
                if (!userMenu.contains(e.target)) {
                    userMenu.classList.remove('open');
                }
            });
        }
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initAuth();
});
