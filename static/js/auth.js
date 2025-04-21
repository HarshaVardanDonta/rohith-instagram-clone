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
        const dropdown = userMenu.querySelector('.user-dropdown');
        
        if (userAvatar) {
            // For click events (especially on mobile)
            userAvatar.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                // Toggle dropdown visibility
                if (dropdown.style.opacity === '1') {
                    dropdown.style.opacity = '0';
                    dropdown.style.visibility = 'hidden';
                    dropdown.style.transform = 'translateY(10px)';
                } else {
                    dropdown.style.opacity = '1';
                    dropdown.style.visibility = 'visible';
                    dropdown.style.transform = 'translateY(0)';
                }
            });
            
            // Close dropdown when clicking outside
            document.addEventListener('click', function(e) {
                if (!userMenu.contains(e.target)) {
                    dropdown.style.opacity = '0';
                    dropdown.style.visibility = 'hidden';
                    dropdown.style.transform = 'translateY(10px)';
                }
            });
            
            // For accessibility - allow keyboard navigation
            userAvatar.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    dropdown.style.opacity = '1';
                    dropdown.style.visibility = 'visible';
                    dropdown.style.transform = 'translateY(0)';
                }
            });
        }
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initAuth();
});
