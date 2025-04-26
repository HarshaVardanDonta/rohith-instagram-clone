/**
 * Universal Post Dialog Module
 * Provides functionality for viewing, liking, and commenting on posts
 */
class PostDialog {
    constructor() {
        // Modal elements
        this.modal = document.getElementById('post-modal');
        this.closeBtn = document.querySelector('.close-modal');
        this.modalContent = document.querySelector('.modal-content');
        
        // Post content elements
        this.modalImage = document.getElementById('modal-post-image');
        this.modalUserAvatar = document.getElementById('modal-user-avatar');
        this.modalUsername = document.getElementById('modal-username');
        this.modalPostTimestamp = document.getElementById('modal-post-timestamp');
        this.modalDescription = document.getElementById('modal-description');
        this.modalLikes = document.getElementById('modal-likes');
        this.modalLikeIcon = document.querySelector('.post-likes i');
        this.modalCommentsCount = document.getElementById('modal-comments-count');
        this.modalPostDate = document.getElementById('modal-post-date');
        this.commentsList = document.getElementById('modal-comments');
        
        // Comment form elements
        this.commentInput = document.getElementById('comment-input');
        this.commentBtn = document.getElementById('post-comment-btn');
        
        // Current post data
        this.currentPost = null;
        this.currentUser = null;
        this.isLiked = false;
        
        // State variables
        this.isImageZoomed = false;
        this.currentImageScale = 1;
        
        // Initialize event listeners
        this.initEventListeners();
    }
    
    /**
     * Initialize all event listeners for the dialog
     */
    initEventListeners() {
        // Close button event
        if (this.closeBtn) {
            this.closeBtn.addEventListener('click', () => this.closeModal());
        }
        
        // Click outside to close
        window.addEventListener('click', (event) => {
            if (event.target === this.modal) {
                this.closeModal();
            }
        });
        
        // ESC key to close
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && this.modal && this.modal.classList.contains('show')) {
                this.closeModal();
            }
        });
        
        // Like button event
        const likeButton = document.querySelector('.post-likes');
        if (likeButton) {
            likeButton.addEventListener('click', () => this.toggleLike());
        }
        
        // Comment button event
        if (this.commentBtn) {
            this.commentBtn.addEventListener('click', () => this.postComment());
        }
        
        // Comment input enter key event
        if (this.commentInput) {
            this.commentInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.postComment();
                }
            });
        }
        
        // Image pan functionality
        if (this.modalImage) {
            this.modalImage.addEventListener('mousedown', (e) => this.handleImageMouseDown(e));
        }
    }
    
    /**
     * Open the post dialog with the provided post data
     * @param {Object} postData - Data for the post to display
     * @param {Object} userData - Current user data
     */
    async openPostDialog(postData, userData) {
        this.currentPost = postData;
        this.currentUser = userData;
        
        if (!this.modal) {
            console.error('Post modal element not found');
            return;
        }
        
        // Show loading state
        this.showImageLoading();
        
        // Show the modal first (makes transition smoother)
        this.modal.classList.add('show');
        
        // Prevent body scrolling
        document.body.style.overflow = 'hidden';
        
        // After a short delay, populate data and show content
        setTimeout(async () => {
            // Populate post data
            this.modalImage.src = postData.imageUrl;
            this.modalUserAvatar.src = postData.userPhotoURL || '';
            this.modalUsername.textContent = postData.username;
            this.modalPostTimestamp.textContent = this.formatPostDate(postData.createdAt);
            this.modalDescription.textContent = postData.description;
            this.modalLikes.textContent = postData.likes || 0;
            this.modalCommentsCount.textContent = postData.comments || 0;
            this.modalPostDate.textContent = this.formatPostDate(postData.createdAt);
            
            // Set post ID as data attribute for reference
            this.modalContent.setAttribute('data-post-id', postData.postId);
            
            // Check if user has already liked this post
            await this.checkLikeStatus();
            
            // Load comments
            await this.loadComments();
            
            // Image onload event
            this.modalImage.onload = () => {
                this.hideImageLoading();
                this.addImageControls();
            };
            
            // If image is cached, it might load before onload triggers
            if (this.modalImage.complete) {
                this.hideImageLoading();
                this.addImageControls();
            }
            
            // Reset zoom state
            this.isImageZoomed = false;
            this.currentImageScale = 1;
            this.modalImage.style.transform = 'scale(1)';
            
            // Update zoom buttons if they exist
            const zoomInBtn = document.querySelector('.zoom-in');
            const zoomOutBtn = document.querySelector('.zoom-out');
            if (zoomInBtn && zoomOutBtn) {
                zoomInBtn.style.display = 'flex';
                zoomOutBtn.style.display = 'none';
            }
        }, 50);
    }
    
    /**
     * Close the post dialog
     */
    closeModal() {
        if (!this.modal) return;
        
        this.modal.classList.remove('show');
        document.body.style.overflow = 'auto';
        
        // Reset image transform after transition
        setTimeout(() => {
            if (this.modalImage) {
                this.modalImage.style.transform = 'scale(1) translate(0, 0)';
            }
            this.isImageZoomed = false;
            this.currentImageScale = 1;
            
            // Clear comment input
            if (this.commentInput) {
                this.commentInput.value = '';
            }
        }, 300);
    }
    
    /**
     * Show image loading state
     */
    showImageLoading() {
        if (this.modalImage) {
            this.modalImage.classList.add('image-loading');
        }
    }
    
    /**
     * Hide image loading state
     */
    hideImageLoading() {
        if (this.modalImage) {
            this.modalImage.classList.remove('image-loading');
        }
    }
    
    /**
     * Format post date in a user-friendly way
     * @param {string|object} dateString - Date string or timestamp
     * @returns {string} Formatted date string
     */
    formatPostDate(dateString) {
        if (!dateString) return '';
        
        // Try to parse the date - handle different formats
        let date;
        
        // Convert Firestore timestamp to Date if needed
        if (dateString && dateString.seconds) {
            date = new Date(dateString.seconds * 1000);
        } else if (dateString && dateString.toDate) {
            date = dateString.toDate();
        } else if (typeof dateString === 'string') {
            if (dateString.includes('GMT')) {
                date = new Date(dateString);
            } else {
                // For simple month/day/year format
                const parts = dateString.split(/[,\s]+/);
                if (parts.length >= 2) {
                    date = new Date(dateString);
                }
            }
        } else if (dateString instanceof Date) {
            date = dateString;
        } else if (typeof dateString === 'number') {
            date = new Date(dateString);
        }
        
        if (!date || isNaN(date.getTime())) return dateString;
        
        // Format the date
        const now = new Date();
        const diffMs = now - date;
        const diffSecs = Math.floor(diffMs / 1000);
        const diffMins = Math.floor(diffSecs / 60);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);
        
        // Return relative time for recent posts
        if (diffDays === 0) {
            if (diffHours === 0) {
                if (diffMins === 0) {
                    return 'Just now';
                }
                return `${diffMins} minute${diffMins !== 1 ? 's' : ''} ago`;
            }
            return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
        } else if (diffDays < 7) {
            return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
        } else {
            // Format as Month Day, Year for older posts
            const options = { year: 'numeric', month: 'short', day: 'numeric' };
            return date.toLocaleDateString(undefined, options);
        }
    }
    
    /**
     * Add image controls to the modal
     */
    addImageControls() {
        // Create image controls container if it doesn't exist
        if (!document.querySelector('.image-controls')) {
            const imageContainer = document.querySelector('.post-image-container');
            const controlsDiv = document.createElement('div');
            controlsDiv.className = 'image-controls';
            
            // Create zoom in button
            const zoomInBtn = document.createElement('div');
            zoomInBtn.className = 'image-control-btn zoom-in';
            zoomInBtn.innerHTML = '<i class="fas fa-search-plus"></i>';
            zoomInBtn.title = 'Zoom In';
            
            // Create zoom out button
            const zoomOutBtn = document.createElement('div');
            zoomOutBtn.className = 'image-control-btn zoom-out';
            zoomOutBtn.innerHTML = '<i class="fas fa-search-minus"></i>';
            zoomOutBtn.title = 'Zoom Out';
            zoomOutBtn.style.display = 'none';
            
            // Create download button
            const downloadBtn = document.createElement('div');
            downloadBtn.className = 'image-control-btn download';
            downloadBtn.innerHTML = '<i class="fas fa-download"></i>';
            downloadBtn.title = 'Download Image';
            
            // Add buttons to controls
            controlsDiv.appendChild(zoomInBtn);
            controlsDiv.appendChild(zoomOutBtn);
            controlsDiv.appendChild(downloadBtn);
            
            // Add controls to image container
            imageContainer.appendChild(controlsDiv);
            
            // Zoom in functionality
            zoomInBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.modalImage.style.transform = 'scale(1.5)';
                this.isImageZoomed = true;
                this.currentImageScale = 1.5;
                zoomInBtn.style.display = 'none';
                zoomOutBtn.style.display = 'flex';
            });
            
            // Zoom out functionality
            zoomOutBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.modalImage.style.transform = 'scale(1)';
                this.isImageZoomed = false;
                this.currentImageScale = 1;
                zoomOutBtn.style.display = 'none';
                zoomInBtn.style.display = 'flex';
            });
            
            // Download functionality
            downloadBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                if (this.modalImage.src) {
                    const link = document.createElement('a');
                    link.href = this.modalImage.src;
                    link.download = 'social_post_image.jpg';
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                }
            });
        }
    }
    
    /**
     * Handle mouse down on image for panning when zoomed
     * @param {Event} e - Mouse event
     */
    handleImageMouseDown(e) {
        if (!this.isImageZoomed) return;
        
        e.preventDefault();
        
        // Get initial cursor position
        const startX = e.clientX;
        const startY = e.clientY;
        
        // Get initial image position
        const initialStyle = window.getComputedStyle(this.modalImage);
        const matrix = new DOMMatrix(initialStyle.transform);
        const initialTranslateX = matrix.m41;
        const initialTranslateY = matrix.m42;
        
        // Mouse move handler for panning
        const handleMouseMove = (e) => {
            const dx = e.clientX - startX;
            const dy = e.clientY - startY;
            
            // Update image position (with scale factor)
            this.modalImage.style.transform = `scale(${this.currentImageScale}) translate(${(initialTranslateX + dx / this.currentImageScale)}px, ${(initialTranslateY + dy / this.currentImageScale)}px)`;
        };
        
        // Mouse up handler to stop panning
        const handleMouseUp = () => {
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
        };
        
        // Add event listeners for mouse move and up
        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
    }
    
    /**
     * Check if the current user has liked this post
     * @returns {Promise<void>}
     */
    async checkLikeStatus() {
        if (!firebase || !firebase.firestore || !this.currentPost || !this.currentUser) {
            return;
        }
        
        try {
            const postId = this.currentPost.postId;
            const userId = this.currentUser.uid;
            
            const likeRef = await firebase.firestore()
                .collection('Posts')
                .doc(postId)
                .collection('Likes')
                .doc(userId)
                .get();
                
            if (likeRef.exists) {
                // User has liked this post
                this.isLiked = true;
                this.modalLikeIcon.classList.add('liked');
                this.modalLikeIcon.style.color = '#e74c3c';
            } else {
                // User hasn't liked this post
                this.isLiked = false;
                this.modalLikeIcon.classList.remove('liked');
                this.modalLikeIcon.style.color = '';
            }
        } catch (error) {
            console.error('Error checking like status:', error);
        }
    }
    
    /**
     * Toggle like status on the current post
     */
    async toggleLike() {
        if (!firebase || !firebase.firestore || !this.currentPost || !this.currentUser) {
            console.error("Can't toggle like: Firebase, post data or user data not available");
            return;
        }
        
        try {
            const postId = this.currentPost.postId;
            const userId = this.currentUser.uid;
            const db = firebase.firestore();
            const postRef = db.collection('Posts').doc(postId);
            const userLikeRef = postRef.collection('Likes').doc(userId);
            
            // Get current post data
            const postDoc = await postRef.get();
            const post = postDoc.data();
            
            if (this.isLiked) {
                // Unlike the post
                await db.runTransaction(async (transaction) => {
                    // Delete the like document
                    transaction.delete(userLikeRef);
                    
                    // Decrement post likes counter
                    const newLikes = (post.likes || 0) - 1;
                    transaction.update(postRef, { likes: Math.max(0, newLikes) });
                    
                    // Update UI
                    this.modalLikes.textContent = Math.max(0, newLikes);
                    this.modalLikeIcon.classList.remove('liked');
                    this.modalLikeIcon.style.color = '';
                    this.isLiked = false;
                    
                    console.log(`User ${userId} unliked post ${postId}`);
                });
            } else {
                // Like the post
                await db.runTransaction(async (transaction) => {
                    // Create a like document with timestamp
                    transaction.set(userLikeRef, { 
                        userId: userId,
                        username: this.currentUser.username,
                        userPhotoURL: this.currentUser.photoURL || null,
                        createdAt: firebase.firestore.FieldValue.serverTimestamp()
                    });
                    
                    // Increment post likes counter
                    const newLikes = (post.likes || 0) + 1;
                    transaction.update(postRef, { likes: newLikes });
                    
                    // Update UI
                    this.modalLikes.textContent = newLikes;
                    this.modalLikeIcon.classList.add('liked');
                    this.modalLikeIcon.style.color = '#e74c3c';
                    this.isLiked = true;
                    
                    // Add like animation
                    const likeButton = document.querySelector('.post-likes');
                    const likeAnim = document.createElement('div');
                    likeAnim.className = 'like-animation';
                    likeButton.appendChild(likeAnim);
                    setTimeout(() => likeButton.removeChild(likeAnim), 700);
                    
                    console.log(`User ${userId} liked post ${postId}`);
                });
            }
            
            // Update like count in the current post data
            this.currentPost.likes = parseInt(this.modalLikes.textContent);
            
            // Also update in the main UI if we have a post element with this ID
            const originalPostElement = document.querySelector(`.post-item[data-post-id="${postId}"]`);
            if (originalPostElement) {
                const likesElement = originalPostElement.querySelector('.fa-heart').nextSibling;
                if (likesElement) {
                    likesElement.textContent = ` ${this.currentPost.likes}`;
                }
            }
            
        } catch (error) {
            console.error('Error toggling like:', error);
        }
    }
    
    /**
     * Load comments for the current post
     */
    async loadComments() {
        if (!firebase || !firebase.firestore || !this.currentPost) {
            console.error("Can't load comments: Firebase or post data not available");
            return;
        }
        
        try {
            const postId = this.currentPost.postId;
            const db = firebase.firestore();
            
            // Query comments, ordered by creation time
            const commentsSnapshot = await db
                .collection('Posts')
                .doc(postId)
                .collection('Comments')
                .orderBy('createdAt', 'desc')
                .limit(50)
                .get();
                
            // Clear comments container
            this.commentsList.innerHTML = '';
            
            // Add comments to UI
            if (commentsSnapshot.empty) {
                this.commentsList.innerHTML = `
                    <p class="no-comments">No comments yet.</p>
                `;
            } else {
                // Create a document fragment to optimize DOM manipulation
                const fragment = document.createDocumentFragment();
                
                commentsSnapshot.forEach(doc => {
                    const comment = doc.data();
                    const commentElement = document.createElement('div');
                    commentElement.className = 'comment-item';
                    
                    const commentDate = comment.createdAt ? this.formatPostDate(comment.createdAt) : '';
                    
                    commentElement.innerHTML = `
                        <div class="comment-user-avatar">
                            <img src="${comment.userPhotoURL || ''}" alt="${comment.username}" 
                                onerror="this.onerror=null; this.src='https://via.placeholder.com/36?text=${comment.username?.charAt(0) || 'U'}'">
                        </div>
                        <div class="comment-content">
                            <div class="comment-header">
                                <span class="comment-username">${comment.username || 'Unknown user'}</span>
                                <span class="comment-timestamp">${commentDate}</span>
                            </div>
                            <div class="comment-text">${this.escapeHtml(comment.text)}</div>
                        </div>
                    `;
                    
                    fragment.appendChild(commentElement);
                });
                
                this.commentsList.appendChild(fragment);
            }
        } catch (error) {
            console.error('Error loading comments:', error);
            this.commentsList.innerHTML = `
                <p class="no-comments error">Error loading comments. Please try again later.</p>
            `;
        }
    }
    
    /**
     * Post a new comment on the current post
     */
    async postComment() {
        if (!firebase || !firebase.firestore || !this.currentPost || !this.currentUser) {
            console.error("Can't post comment: Firebase, post data or user data not available");
            return;
        }
        
        // Get comment text
        const commentText = this.commentInput.value.trim();
        if (!commentText) {
            return; // Don't post empty comments
        }
        
        try {
            const postId = this.currentPost.postId;
            const userId = this.currentUser.uid;
            const db = firebase.firestore();
            const postRef = db.collection('Posts').doc(postId);
            
            // Create a new comment document with a generated ID
            const newCommentRef = postRef.collection('Comments').doc();
            
            // Show temporary loading state in input
            this.commentInput.disabled = true;
            this.commentBtn.disabled = true;
            this.commentBtn.textContent = 'Posting...';
            
            // Get current post data
            const postDoc = await postRef.get();
            const post = postDoc.data();
            
            await db.runTransaction(async (transaction) => {
                // Create the comment document
                transaction.set(newCommentRef, {
                    commentId: newCommentRef.id,
                    postId: postId,
                    userId: userId,
                    username: this.currentUser.username,
                    userPhotoURL: this.currentUser.photoURL || null,
                    text: commentText,
                    createdAt: firebase.firestore.FieldValue.serverTimestamp()
                });
                
                // Increment post comments counter
                const newCommentCount = (post.comments || 0) + 1;
                transaction.update(postRef, { comments: newCommentCount });
                
                // Update UI
                this.modalCommentsCount.textContent = newCommentCount;
                this.currentPost.comments = newCommentCount;
                
                // Update comment count in the main UI
                const originalPostElement = document.querySelector(`.post-item[data-post-id="${postId}"]`);
                if (originalPostElement) {
                    const commentsElement = originalPostElement.querySelector('.fa-comment').nextSibling;
                    if (commentsElement) {
                        commentsElement.textContent = ` ${newCommentCount}`;
                    }
                }
                
                console.log(`User ${userId} commented on post ${postId}`);
            });
            
            // Clear comment input
            this.commentInput.value = '';
            
            // Reload comments to show the new comment
            await this.loadComments();
            
        } catch (error) {
            console.error('Error posting comment:', error);
            alert('Failed to post comment. Please try again.');
        } finally {
            // Reset UI
            this.commentInput.disabled = false;
            this.commentBtn.disabled = false;
            this.commentBtn.textContent = 'Post';
        }
    }
    
    /**
     * Escape HTML to prevent XSS attacks
     * @param {string} unsafe - Unsafe HTML string
     * @returns {string} Escaped HTML string
     */
    escapeHtml(unsafe) {
        if (typeof unsafe !== 'string') return '';
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
}

// Create and export the PostDialog instance
const postDialog = new PostDialog();

// Function to open post dialog from anywhere in the app
function openPostDialog(postData, userData) {
    postDialog.openPostDialog(postData, userData);
}