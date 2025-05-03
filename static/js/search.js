document.addEventListener('DOMContentLoaded', function() {
    const searchBox = document.querySelector('.search input');
    
    const resultsBox = document.createElement('div');
    resultsBox.className = 'search-results-container';
    document.querySelector('.search').appendChild(resultsBox);
    
    if (searchBox) {
        searchBox.addEventListener('input', debounce(function() {
            const searchText = searchBox.value.trim();
            
            if (!searchText) {
                resultsBox.innerHTML = '';
                resultsBox.classList.remove('show');
                return;
            }
            
            findUsers(searchText, resultsBox);
        }, 300));
        
        document.addEventListener('click', function(event) {
            if (!event.target.closest('.search')) {
                resultsBox.classList.remove('show');
            }
        });
        
        searchBox.addEventListener('focus', function() {
            const searchText = searchBox.value.trim();
            if (searchText) {
                resultsBox.classList.add('show');
            }
        });
    }
});

function debounce(func, wait) {
    let timeout;
    return function(...args) {
        const context = this;
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(context, args), wait);
    };
}

async function findUsers(query, resultsBox) {
    try {
        const response = await fetch(`/search?query=${encodeURIComponent(query)}`);
        const data = await response.json();
        
        showResults(data.users, resultsBox);
    } catch (error) {
        console.error('Ugh, search failed:', error);
        resultsBox.innerHTML = '<div class="search-error">Something went wrong with the search</div>';
        resultsBox.classList.add('show');
    }
}

function showResults(users, container) {
    container.innerHTML = '';
    
    if (users.length === 0) {
        container.innerHTML = '<div class="no-results">No users found</div>';
        container.classList.add('show');
        return;
    }
    
    const userList = document.createElement('ul');
    userList.className = 'search-results-list';
    
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
        
        userList.appendChild(userItem);
    });
    
    container.appendChild(userList);
    container.classList.add('show');
}