/**
 * Search functionality for finding users by display name
 */

document.addEventListener('DOMContentLoaded', function() {
    // Get the search input element
    const searchInput = document.querySelector('.search input');
    
    // Create search results dropdown container
    const searchResultsContainer = document.createElement('div');
    searchResultsContainer.className = 'search-results-container';
    document.querySelector('.search').appendChild(searchResultsContainer);
    
    // Add event listeners for search input
    if (searchInput) {
        // Handle input event for searching
        searchInput.addEventListener('input', debounce(function() {
            const query = searchInput.value.trim();
            
            // Hide dropdown if query is empty
            if (!query) {
                searchResultsContainer.innerHTML = '';
                searchResultsContainer.classList.remove('show');
                return;
            }
            
            // Perform search
            performSearch(query, searchResultsContainer);
        }, 300));  // 300ms debounce delay
        
        // Handle click outside search dropdown to close it
        document.addEventListener('click', function(event) {
            if (!event.target.closest('.search')) {
                searchResultsContainer.classList.remove('show');
            }
        });
        
        // Handle focus on search input
        searchInput.addEventListener('focus', function() {
            const query = searchInput.value.trim();
            if (query) {
                searchResultsContainer.classList.add('show');
            }
        });
    }
});

// Debounce function to limit API calls
function debounce(func, wait) {
    let timeout;
    return function(...args) {
        const context = this;
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(context, args), wait);
    };
}

// Perform search API call and render results
async function performSearch(query, resultsContainer) {
    try {
        // Call the search endpoint
        const response = await fetch(`/search?query=${encodeURIComponent(query)}`);
        const data = await response.json();
        
        // Render search results
        renderSearchResults(data.users, resultsContainer);
    } catch (error) {
        console.error('Search error:', error);
        resultsContainer.innerHTML = '<div class="search-error">Error occurred while searching</div>';
        resultsContainer.classList.add('show');
    }
}

// Render search results in the dropdown
function renderSearchResults(users, container) {
    // Clear previous results
    container.innerHTML = '';
    
    // If no users found
    if (users.length === 0) {
        container.innerHTML = '<div class="no-results">No users found</div>';
        container.classList.add('show');
        return;
    }
    
    // Create results list
    const resultsList = document.createElement('ul');
    resultsList.className = 'search-results-list';
    
    // Add users to results list
    users.forEach(user => {
        const userItem = document.createElement('li');
        userItem.className = 'search-result-item';
        
        userItem.innerHTML = `
            <a href="/profile/${user.uid}" class="search-result-link">
                <div class="search-result-avatar">
                    ${user.photoURL ? 
                      `<img src="${user.photoURL}" alt="${user.displayName}">` : 
                      `<div class="avatar-placeholder"><i class="fas fa-user"></i></div>`}
                </div>
                <div class="search-result-user-info">
                    <div class="search-result-username">${user.username}</div>
                    <div class="search-result-display-name">${user.displayName}</div>
                </div>
            </a>
        `;
        
        resultsList.appendChild(userItem);
    });
    
    // Add list to container
    container.appendChild(resultsList);
    
    // Show the dropdown
    container.classList.add('show');
}