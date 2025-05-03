// Authentication Helper Functions
// These functions manage user authentication state and UI elements
// Last updated: March 15, 2025 - Fixed dropdown menu issues on mobile devices

/**
 * Checks if the current user is authenticated
 * We can't directly access httpOnly cookies with JavaScript, so we check for a class on the body element
 * @returns {boolean} True if user is authenticated, false otherwise
 */
function checkAuth() {
    return document.body.classList.contains('is-authenticated');
}

/**
 * Initializes the authentication state and related UI elements
 * Shows or hides elements based on user's authentication status
 * Sets up the user dropdown menu behavior
 */
function initAuth() {
    const isUserLoggedIn = checkAuth();
    
    // Show/hide elements based on authentication status
    if (isUserLoggedIn) {
        // Show elements that require authentication
        document.querySelectorAll('.auth-required').forEach(element => {
            element.style.display = 'block';
        });
        
        // Hide elements that shouldn't appear when authenticated
        document.querySelectorAll('.auth-hidden').forEach(element => {
            element.style.display = 'none';
        });
    } else {
        // Hide elements that require authentication
        document.querySelectorAll('.auth-required').forEach(element => {
            element.style.display = 'none';
        });
        
        // Show elements that appear only when not authenticated
        document.querySelectorAll('.auth-hidden').forEach(element => {
            element.style.display = 'block';
        });
    }
    
    // Setup user profile dropdown menu
    setupUserDropdownMenu();
}

/**
 * Sets up the user dropdown menu behavior
 * Handles click and keyboard events for accessibility
 */
function setupUserDropdownMenu() {
    const userMenu = document.querySelector('.user-menu');
    if (!userMenu) return; // Exit if menu doesn't exist
    
    const userAvatar = userMenu.querySelector('.user-avatar');
    const dropdownMenu = userMenu.querySelector('.user-dropdown');
    
    if (userAvatar && dropdownMenu) {
        // Toggle dropdown menu on avatar click
        userAvatar.addEventListener('click', function(event) {
            event.preventDefault();
            event.stopPropagation();
            
            toggleDropdown(dropdownMenu);
        });
        
        // Close dropdown when clicking outside
        document.addEventListener('click', function(event) {
            if (!userMenu.contains(event.target)) {
                hideDropdown(dropdownMenu);
            }
        });
        
        // Keyboard accessibility - open dropdown with Enter or Space
        userAvatar.addEventListener('keydown', function(event) {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                showDropdown(dropdownMenu);
            }
        });
    }
}

/**
 * Shows the dropdown menu
 * @param {HTMLElement} dropdown - The dropdown element to show
 */
function showDropdown(dropdown) {
    dropdown.style.opacity = '1';
    dropdown.style.visibility = 'visible';
    dropdown.style.transform = 'translateY(0)';
}

/**
 * Hides the dropdown menu
 * @param {HTMLElement} dropdown - The dropdown element to hide
 */
function hideDropdown(dropdown) {
    dropdown.style.opacity = '0';
    dropdown.style.visibility = 'hidden';
    dropdown.style.transform = 'translateY(10px)';
}

/**
 * Toggles the dropdown menu visibility
 * @param {HTMLElement} dropdown - The dropdown element to toggle
 */
function toggleDropdown(dropdown) {
    if (dropdown.style.opacity === '1') {
        hideDropdown(dropdown);
    } else {
        showDropdown(dropdown);
    }
}

// Initialize authentication when the page loads
document.addEventListener('DOMContentLoaded', function() {
    initAuth();
});
