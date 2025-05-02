import os
import json
import requests
import uuid
import io
import firebase_admin
from firebase_admin import credentials, auth, firestore, storage
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from dotenv import load_dotenv
import uvicorn
from starlette.middleware.base import BaseHTTPMiddleware
import time
from datetime import datetime, timedelta
from google.cloud import storage as gcs
from PIL import Image

# Load environment variables
load_dotenv()

# Helper function to compress image
async def compress_image(file_content, content_type, max_size=(1024, 1024), quality=85):
    """
    Compress an image without significant quality loss
    - file_content: The binary content of the image file
    - content_type: The MIME type of the image
    - max_size: The maximum dimensions (width, height) to resize to if larger
    - quality: JPEG/WebP compression quality (0-100)
    
    Returns: (compressed_content, new_content_type)
    """
    try:
        # Create PIL Image object from binary content
        image = Image.open(io.BytesIO(file_content))
        
        # Preserve original format for saving
        if content_type == "image/jpeg" or content_type == "image/jpg":
            format_name = "JPEG"
            new_content_type = "image/jpeg"
        elif content_type == "image/png":
            format_name = "PNG" 
            new_content_type = "image/png"
        elif content_type == "image/gif":
            format_name = "GIF"
            new_content_type = "image/gif"
        elif content_type == "image/webp":
            format_name = "WEBP"
            new_content_type = "image/webp"
        else:
            # Default to JPEG for unknown formats
            format_name = "JPEG"
            new_content_type = "image/jpeg"
        
        # Resize if the image is larger than max_size
        if image.width > max_size[0] or image.height > max_size[1]:
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Save the processed image
        output = io.BytesIO()
        
        # PNG should be compressed differently (no quality parameter)
        if format_name == "PNG":
            image.save(output, format=format_name, optimize=True)
        elif format_name == "GIF":
            # GIF doesn't use quality param
            image.save(output, format=format_name)
        else:
            # JPEG and WEBP use quality param
            image.save(output, format=format_name, quality=quality, optimize=True)
        
        output.seek(0)
        return output.getvalue(), new_content_type
    except Exception as e:
        print(f"Image compression error: {str(e)}")
        # Return original content if compression fails
        return file_content, content_type

# Initialize Firebase with service account for auth and Firestore
firebase_cred_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
gcs_cred_path = os.getenv('GOOGLE_CLOUD_SERVICE_ACCOUNT_PATH')
bucket_name = os.getenv('GOOGLE_CLOUD_STORAGE_BUCKET')  # Get bucket name from environment

try:
    # Initialize Firebase with the Firebase service account
    if firebase_cred_path and os.path.exists(firebase_cred_path):
        cred = credentials.Certificate(firebase_cred_path)
        firebase_admin.initialize_app(cred, {
            'projectId': os.getenv('FIREBASE_PROJECT_ID'),
        })
    else:
        # Fallback to default credentials if path not provided or file doesn't exist
        firebase_admin.initialize_app(options={
            'projectId': os.getenv('FIREBASE_PROJECT_ID'),
        })
except ValueError as e:
    # If already initialized or error, print the error message and continue
    print(f"Firebase initialization note: {e}")

# Initialize Firestore client
db = firestore.client()

# Initialize Google Cloud Storage client with separate service account
gcs_client = None
try:
    if gcs_cred_path and os.path.exists(gcs_cred_path):
        gcs_client = gcs.Client.from_service_account_json(gcs_cred_path)
        print("Google Cloud Storage client initialized with service account")
    else:
        print("Warning: Google Cloud Storage service account path not found or invalid")
        # Fallback to default credentials
        gcs_client = gcs.Client()
except Exception as e:
    print(f"Error initializing Google Cloud Storage client: {e}")

# Create FastAPI app
app = FastAPI(title="Social")

# Authentication middleware
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Paths that don't require authentication
        public_paths = ['/login', '/signup', '/forgot-password', '/static', '/favicon.ico']
        
        # Check if the path is public
        is_public = any(request.url.path.startswith(path) for path in public_paths)
        
        # If not a public path, check for authentication
        if not is_public:
            user_id = request.cookies.get("user_id")
            token = request.cookies.get("auth_token")
            
            # Validate auth token expiry
            token_expiry = request.cookies.get("token_expiry")
            is_token_valid = False
            
            if user_id and token and token_expiry:
                try:
                    # Convert expiry time to datetime
                    expiry_time = datetime.fromtimestamp(float(token_expiry))
                    if expiry_time > datetime.now():
                        is_token_valid = True
                    else:
                        # Token expired, redirect to login
                        response = RedirectResponse(url="/login?message=Session expired. Please log in again.")
                        response.delete_cookie("user_id")
                        response.delete_cookie("auth_token")
                        response.delete_cookie("token_expiry")
                        return response
                except:
                    # Invalid token format
                    pass
            
            # If not authenticated, redirect to login
            if not user_id or not is_token_valid:
                return RedirectResponse(url="/login")
            
            # Add user data to request state
            try:
                user = auth.get_user(user_id)
                request.state.user = user
                
                # Get additional user data from Firestore
                user_doc = db.collection('Users').document(user_id).get()
                if user_doc.exists:
                    request.state.user_data = user_doc.to_dict()
                else:
                    request.state.user_data = {
                        'uid': user.uid,
                        'email': user.email,
                        'displayName': user.display_name,
                        'username': user.display_name.lower().replace(' ', '.') if user.display_name else '',
                        'photoURL': user.photo_url
                    }
            except Exception as e:
                print(f"Error fetching user data in middleware: {e}")
                # If we can't get the user data, redirect to login
                response = RedirectResponse(url="/login")
                response.delete_cookie("user_id")
                response.delete_cookie("auth_token")
                response.delete_cookie("token_expiry")
                return response
        
        # Continue processing the request
        response = await call_next(request)
        return response

# Add middleware to app
app.add_middleware(AuthMiddleware)

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Security
security = HTTPBasic()

# Routes
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Redirect to login page if not authenticated, otherwise to home"""
    user_id = request.cookies.get("user_id")
    if user_id:
        return RedirectResponse(url="/home")
    return RedirectResponse(url="/login")

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    """Render signup page"""
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup")
async def signup(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    username: str = Form(...)
):
    """Create a new user"""
    try:
        # Check if username already exists
        username_query = db.collection('Users').where('username', '==', username).limit(1).get()
        if len(username_query) > 0:
            return templates.TemplateResponse(
                "signup.html", 
                {"request": request, "error": "Username already taken. Please choose a different username."}
            )

        # Create the user in Firebase Authentication
        user = auth.create_user(
            email=email,
            password=password,
            display_name=full_name
        )
        
        # Store user data in Firestore
        try:
            users_ref = db.collection('Users')
            users_ref.document(user.uid).set({
                'uid': user.uid,
                'email': email,
                'displayName': full_name,
                'username': username,
                'createdAt': firestore.SERVER_TIMESTAMP,
                'lastLogin': firestore.SERVER_TIMESTAMP,
                'photoURL': None,
            })
            print(f"User data stored in Firestore for UID: {user.uid}")
        except Exception as db_error:
            print(f"Error storing user data in Firestore: {db_error}")
            # Continue the process even if Firestore storage fails
            # We can try to update the data during login
        
        # Success - redirect to login page
        return RedirectResponse(url="/login?message=Account created! Please log in.", status_code=status.HTTP_303_SEE_OTHER)
    
    except firebase_admin.exceptions.FirebaseError as e:
        error_message = "An error occurred during signup. Please try again."
        error_code = getattr(e, 'code', None)
        
        # Handle specific Firebase error codes
        if error_code == 'EMAIL_EXISTS' or 'email-already-exists' in str(e).lower():
            error_message = "Email already in use. Please use a different email."
        elif error_code == 'INVALID_EMAIL' or 'invalid-email' in str(e).lower():
            error_message = "The email address is not valid."
        elif error_code == 'WEAK_PASSWORD' or 'weak-password' in str(e).lower():
            error_message = "Password is too weak. Please use a stronger password (at least 6 characters)."
        
        print(f"Firebase error during signup: {str(e)}")
        return templates.TemplateResponse(
            "signup.html", 
            {"request": request, "error": error_message}
        )
    
    except Exception as e:
        # Log the full error for debugging purposes
        print(f"Unexpected error during signup: {str(e)}")
        
        return templates.TemplateResponse(
            "signup.html", 
            {"request": request, "error": "An unexpected error occurred. Please try again later."}
        )

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, message: str = None):
    """Render login page"""
    return templates.TemplateResponse(
        "login.html", 
        {"request": request, "message": message}
    )

@app.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
):
    """Log in a user"""
    try:
        # For development purposes, we'll simulate successful login
        # In a production app, you would validate credentials with Firebase
        # Since firebase_admin doesn't provide email/password sign-in directly
        # You would typically use Firebase client SDK for auth in the frontend
        
        # Get a user by email (to verify the user exists)
        try:
            user = auth.get_user_by_email(email)
            # Note: We can't verify the password with firebase_admin
            # This is just a check that the user exists
            
            # Generate a custom token for the user (in real implementation, this would verify the password)
            token = str(uuid.uuid4())
            
            # Set token expiry to 7 days from now
            token_expiry = datetime.now() + timedelta(days=7)
            
            # Store or update user data in Firestore
            try:
                users_ref = db.collection('Users')
                users_ref.document(user.uid).set({
                    'uid': user.uid,
                    'email': user.email,
                    'displayName': user.display_name,
                    'lastLogin': firestore.SERVER_TIMESTAMP,
                    'photoURL': user.photo_url if user.photo_url else None,
                    'currentToken': token,  # Store the token in Firestore
                    'tokenExpiry': token_expiry.timestamp()
                }, merge=True)  # merge=True will update existing document or create if it doesn't exist
                print(f"User data updated in Firestore for UID: {user.uid}")
            except Exception as db_error:
                print(f"Error updating user data in Firestore: {db_error}")
                # Continue the login process even if Firestore update fails
            
            # Set up session cookies for authentication
            response = RedirectResponse(url="/home", status_code=status.HTTP_303_SEE_OTHER)
            
            # Store authentication data in cookies
            response.set_cookie(
                key="user_id", 
                value=user.uid,
                httponly=True,
                max_age=7 * 24 * 3600,  # 7 days
                secure=False  # Set to True in production with HTTPS
            )
            response.set_cookie(
                key="auth_token", 
                value=token,
                httponly=True,
                max_age=7 * 24 * 3600,  # 7 days
                secure=False  # Set to True in production with HTTPS
            )
            response.set_cookie(
                key="token_expiry", 
                value=str(token_expiry.timestamp()),
                httponly=True,
                max_age=7 * 24 * 3600,  # 7 days
                secure=False  # Set to True in production with HTTPS
            )
            
            return response
            
        except firebase_admin.auth.UserNotFoundError:
            return templates.TemplateResponse(
                "login.html", 
                {"request": request, "error": "Email not found. Please sign up."}
            )
            
    except Exception as e:
        return templates.TemplateResponse(
            "login.html", 
            {"request": request, "error": f"Login failed: {str(e)}"}
        )

@app.get("/home", response_class=HTMLResponse)
async def home(request: Request):
    """Render home page with feed posts from user and followed accounts"""
    # User data is now available in request.state
    user_id = request.state.user.uid
    
    try:
        feed_posts = []
        
        # Get list of users the current user follows
        following_ref = db.collection('Users').document(user_id).collection('Following')
        following_users = [user_id]  # Start with current user's ID
        
        # Add followed users to the list
        for follow_doc in following_ref.stream():
            follow_data = follow_doc.to_dict()
            if 'userId' in follow_data:
                following_users.append(follow_data['userId'])
        
        # For each user (including current user), get their posts
        for followed_user_id in following_users:
            # Get posts from this user
            user_posts_ref = db.collection('Posts').where('userId', '==', followed_user_id).order_by('createdAt', direction=firestore.Query.DESCENDING)
            
            for post in user_posts_ref.stream():
                post_data = post.to_dict()
                # Add post ID if not present in the data
                if 'postId' not in post_data:
                    post_data['postId'] = post.id
                
                # Fetch top 5 comments for this post
                try:
                    comments_ref = db.collection('Posts').document(post_data['postId']).collection('Comments').order_by('createdAt', direction=firestore.Query.DESCENDING).limit(5)
                    comments = []
                    for comment_doc in comments_ref.stream():
                        comment_data = comment_doc.to_dict()
                        comments.append(comment_data)
                    
                    # Add the comments to the post data
                    post_data['top_comments'] = comments
                except Exception as e:
                    print(f"Error fetching comments for post {post_data['postId']}: {str(e)}")
                    post_data['top_comments'] = []
                
                feed_posts.append(post_data)
        
        # Sort all collected posts by creation time (most recent first)
        feed_posts.sort(key=lambda x: x.get('createdAt', 0), reverse=True)
        
        # Limit to 50 posts
        feed_posts = feed_posts[:50]
            
        return templates.TemplateResponse("home.html", {
            "request": request, 
            "user": request.state.user,
            "user_data": request.state.user_data,
            "feed_posts": feed_posts
        })
    except Exception as e:
        print(f"Error fetching feed posts: {str(e)}")
        # If there's an error, still render the page but without posts
        return templates.TemplateResponse("home.html", {
            "request": request, 
            "user": request.state.user,
            "user_data": request.state.user_data,
            "feed_posts": []
        })

@app.get("/logout")
async def logout():
    """Log out a user"""
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    # Clear cookies
    response.delete_cookie("user_id")
    response.delete_cookie("auth_token")
    response.delete_cookie("token_expiry")
    return response

@app.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    """Render forgot password page"""
    return templates.TemplateResponse(
        "forgot_password.html", 
        {"request": request}
    )

@app.post("/forgot-password")
async def forgot_password(
    request: Request,
    email: str = Form(...)
):
    """Send password reset email"""
    try:
        # Generate password reset link
        reset_link = auth.generate_password_reset_link(email)
        
        # In a production app, you would send this link via email
        # Here we just show it on the UI for demonstration
        return templates.TemplateResponse(
            "forgot_password.html", 
            {
                "request": request, 
                "message": "Password reset link has been sent to your email.",
                "reset_link": reset_link  # Remove this in production
            }
        )
    except firebase_admin.auth.UserNotFoundError:
        return templates.TemplateResponse(
            "forgot_password.html", 
            {"request": request, "error": "Email not found. Please sign up."}
        )
    except Exception as e:
        return templates.TemplateResponse(
            "forgot_password.html", 
            {"request": request, "error": f"An error occurred: {str(e)}"}
        )

@app.get("/profile", response_class=HTMLResponse)
async def profile(request: Request):
    """Render profile page"""
    # User data is now available in request.state
    user_id = request.state.user.uid
    
    try:
        # Fetch user's posts from Firestore in reverse chronological order
        posts_ref = db.collection('Posts').where('userId', '==', user_id).order_by('createdAt', direction=firestore.Query.DESCENDING).limit(30)
        posts = []
        
        # Get the posts and format them for the template
        for post in posts_ref.stream():
            post_data = post.to_dict()
            # Add post ID if not present in the data
            if 'postId' not in post_data:
                post_data['postId'] = post.id
            posts.append(post_data)
        
        # Count the posts
        post_count = len(posts)
        
        # Update user_data with post count
        user_data = request.state.user_data
        user_data['post_count'] = post_count
        
        return templates.TemplateResponse(
            "profile.html", 
            {
                "request": request, 
                "user": request.state.user,
                "user_data": user_data,
                "posts": posts
            }
        )
    except Exception as e:
        print(f"Error fetching posts: {str(e)}")
        # If there's an error, still render the page but without posts
        return templates.TemplateResponse(
            "profile.html", 
            {
                "request": request, 
                "user": request.state.user,
                "user_data": request.state.user_data,
                "posts": []
            }
        )

@app.get("/edit-profile", response_class=HTMLResponse)
async def edit_profile_page(request: Request):
    """Render edit profile page"""
    # Get the user ID from cookie
    user_id = request.cookies.get("user_id")
    
    # Check if user is authenticated
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    try:
        # Verify the user exists in Firebase
        user = auth.get_user(user_id)
        
        # Get user data from Firestore
        user_doc = db.collection('Users').document(user_id).get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
        else:
            user_data = {
                'uid': user.uid,
                'email': user.email,
                'displayName': user.display_name,
                'username': user.display_name.lower().replace(' ', '.'),
                'photoURL': user.photo_url
            }
        
        # Render the edit profile page
        return templates.TemplateResponse(
            "edit_profile.html", 
            {
                "request": request, 
                "user": user,
                "user_data": user_data
            }
        )
    except Exception as e:
        print(f"Edit profile error: {str(e)}")
        response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        response.delete_cookie("user_id")
        return response

@app.post("/edit-profile")
async def edit_profile(
    request: Request,
    username: str = Form(...),
    full_name: str = Form(...),
    profile_photo: UploadFile = File(None)
):
    """Update user profile"""
    # Get the user ID from cookie
    user_id = request.cookies.get("user_id")
    
    # Check if user is authenticated
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    try:
        # Verify the user exists in Firebase
        user = auth.get_user(user_id)
        
        # Initialize updates dictionary
        updates = {
            'username': username,
            'displayName': full_name
        }
        
        # Check if a profile photo was uploaded
        if profile_photo and profile_photo.filename:
            try:
                # Create a unique filename to avoid overwriting
                file_extension = os.path.splitext(profile_photo.filename)[1]
                file_name = f"profile_photos/{user_id}/{uuid.uuid4()}{file_extension}"
                
                # Read the file content
                file_content = await profile_photo.read()
                
                # Compress the image
                compressed_content, content_type = await compress_image(file_content, profile_photo.content_type)
                
                # Upload the file to Firebase Storage
                blob = gcs_client.bucket(bucket_name).blob(file_name)
                blob.upload_from_string(
                    compressed_content,
                    content_type=content_type
                )
                
                # Make the blob publicly accessible
                blob.make_public()
                
                # Get the public URL
                image_url = blob.public_url
                
                # Add to updates
                updates['photoURL'] = image_url
                
                # Update user profile in Firebase Auth
                auth.update_user(
                    user_id,
                    display_name=full_name,
                    photo_url=image_url
                )
            except Exception as storage_error:
                print(f"Profile photo upload error: {storage_error}")
                return templates.TemplateResponse(
                    "edit_profile.html", 
                    {
                        "request": request, 
                        "user": user,
                        "user_data": updates,
                        "error": "Failed to upload profile photo. Please try again."
                    }
                )
        else:
            # Update user profile in Firebase Auth (without photo)
            auth.update_user(
                user_id,
                display_name=full_name
            )
        
        # Update user data in Firestore
        db.collection('Users').document(user_id).update(updates)
        
        # Redirect to profile page with success message
        return RedirectResponse(url="/profile?message=Profile updated successfully", status_code=status.HTTP_303_SEE_OTHER)
        
    except Exception as e:
        print(f"Profile update error: {str(e)}")
        # Get the current user data for the error response
        user_doc = db.collection('Users').document(user_id).get()
        user_data = user_doc.to_dict() if user_doc.exists else {}
        
        return templates.TemplateResponse(
            "edit_profile.html", 
            {
                "request": request, 
                "user": auth.get_user(user_id),
                "user_data": user_data,
                "error": f"An error occurred: {str(e)}"
            }
        )

@app.get("/create", response_class=HTMLResponse)
async def create_post_page(request: Request):
    """Render create post page"""
    return templates.TemplateResponse("create_post.html", {
        "request": request, 
        "user": request.state.user,
        "user_data": request.state.user_data
    })

@app.post("/create")
async def create_post(
    request: Request,
    description: str = Form(...),
    image: UploadFile = File(...)
):
    """Create a new post with description and image"""
    # Get the user ID from request state
    user_id = request.state.user.uid
    
    try:
        # Check if image is valid
        if not image or not image.filename:
            return templates.TemplateResponse(
                "create_post.html", 
                {
                    "request": request, 
                    "error": "Image file is required"
                }
            )
            
        # Check file type
        allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
        if image.content_type not in allowed_types:
            return templates.TemplateResponse(
                "create_post.html", 
                {
                    "request": request, 
                    "error": "Only JPEG, PNG, GIF, and WebP images are allowed"
                }
            )
        
        # Create a unique filename to avoid overwriting
        post_id = str(uuid.uuid4())
        file_extension = os.path.splitext(image.filename)[1]
        file_name = f"posts/{user_id}/{post_id}{file_extension}"
        
        # Read the file content
        file_content = await image.read()
        
        # Compress the image
        compressed_content, content_type = await compress_image(file_content, image.content_type)
        
        # Upload the file to Firebase Storage
        blob = gcs_client.bucket(bucket_name).blob(file_name)
        blob.upload_from_string(
            compressed_content,
            content_type=content_type
        )
        
        # Make the blob publicly accessible
        blob.make_public()
        
        # Get the public URL
        image_url = blob.public_url
        
        print(f"Successfully uploaded image to: {file_name}")
        
        # Create post data
        post_data = {
            'postId': post_id,
            'userId': user_id,
            'description': description,
            'imageUrl': image_url,
            'imagePath': file_name,  # Store the path for future reference
            'createdAt': firestore.SERVER_TIMESTAMP,
            'likes': 0,
            'comments': 0
        }
        
        # Add username and user photo URL to post data
        user_data = request.state.user_data
        post_data['username'] = user_data.get('username', '')
        post_data['userPhotoURL'] = user_data.get('photoURL', '')
        
        # Store post data in Firestore
        db.collection('Posts').document(post_id).set(post_data)
        
        # Also add to user's posts collection
        db.collection('Users').document(user_id).collection('Posts').document(post_id).set({
            'postId': post_id,
            'createdAt': firestore.SERVER_TIMESTAMP
        })
        
        # Redirect to home page with success message
        return RedirectResponse(url="/home?message=Post created successfully", status_code=status.HTTP_303_SEE_OTHER)
        
    except Exception as e:
        print(f"Post creation error: {str(e)}")
        return templates.TemplateResponse(
            "create_post.html", 
            {
                "request": request,
                "user": request.state.user,
                "user_data": request.state.user_data,
                "error": f"Failed to create post: {str(e)}"
            }
        )

@app.get("/followers/{user_id}", response_class=HTMLResponse)
async def followers_page(request: Request, user_id: str):
    """Show the list of followers for a user"""
    try:
        # Check if the profile user exists
        try:
            profile_user = auth.get_user(user_id)
        except:
            # If the user doesn't exist, redirect to home
            return RedirectResponse(url="/home", status_code=status.HTTP_303_SEE_OTHER)
        
        # Get the followers from Firestore
        followers_ref = db.collection('Users').document(user_id).collection('Followers')
        followers_query = followers_ref.order_by('createdAt', direction=firestore.Query.DESCENDING)
        
        # Fetch all followers and their data
        followers = []
        for doc in followers_query.stream():
            follower_data = doc.to_dict()
            if 'userId' in follower_data:
                # Get the follower's user data
                follower_user_doc = db.collection('Users').document(follower_data['userId']).get()
                if follower_user_doc.exists:
                    follower_user = follower_user_doc.to_dict()
                    followers.append({
                        'uid': follower_data['userId'],
                        'username': follower_user.get('username', ''),
                        'displayName': follower_user.get('displayName', ''),
                        'photoURL': follower_user.get('photoURL', None)
                    })
        
        return templates.TemplateResponse("followers.html", {
            "request": request,
            "user_data": request.state.user_data,
            "profile_user_id": user_id,
            "followers": followers
        })
        
    except Exception as e:
        print(f"Error fetching followers: {e}")
        return templates.TemplateResponse("followers.html", {
            "request": request,
            "user_data": request.state.user_data,
            "profile_user_id": user_id,
            "followers": []
        })

@app.get("/following/{user_id}", response_class=HTMLResponse)
async def following_page(request: Request, user_id: str):
    """Show the list of users that a user is following"""
    try:
        # Check if the profile user exists
        try:
            profile_user = auth.get_user(user_id)
        except:
            # If the user doesn't exist, redirect to home
            return RedirectResponse(url="/home", status_code=status.HTTP_303_SEE_OTHER)
        
        # Get the following users from Firestore
        following_ref = db.collection('Users').document(user_id).collection('Following')
        following_query = following_ref.order_by('createdAt', direction=firestore.Query.DESCENDING)
        
        # Fetch all following and their data
        following = []
        for doc in following_query.stream():
            following_data = doc.to_dict()
            if 'userId' in following_data:
                # Get the followed user's data
                followed_user_doc = db.collection('Users').document(following_data['userId']).get()
                if followed_user_doc.exists:
                    followed_user = followed_user_doc.to_dict()
                    following.append({
                        'uid': following_data['userId'],
                        'username': followed_user.get('username', ''),
                        'displayName': followed_user.get('displayName', ''),
                        'photoURL': followed_user.get('photoURL', None)
                    })
        
        return templates.TemplateResponse("following.html", {
            "request": request,
            "user_data": request.state.user_data,
            "profile_user_id": user_id,
            "following": following
        })
        
    except Exception as e:
        print(f"Error fetching following: {e}")
        return templates.TemplateResponse("following.html", {
            "request": request,
            "user_data": request.state.user_data,
            "profile_user_id": user_id,
            "following": []
        })

@app.get("/search")
async def search_users(request: Request, query: str = None):
    """Search for users by display name"""
    results = []
    
    if query and query.strip():
        try:
            # Search for users whose displayName starts with the query (case insensitive)
            query = query.strip().lower()
            
            # Get all users and filter in memory for case-insensitive prefix match
            # Not ideal for large databases, but works for small to medium user bases
            users_ref = db.collection('Users').limit(100).stream()
            
            for doc in users_ref:
                user_data = doc.to_dict()
                display_name = user_data.get('displayName', '').lower()
                
                # Check if display name starts with the query
                if display_name.startswith(query):
                    results.append({
                        'uid': user_data.get('uid'),
                        'username': user_data.get('username'),
                        'displayName': user_data.get('displayName'),
                        'photoURL': user_data.get('photoURL')
                    })
            
            # Sort results by displayName
            results.sort(key=lambda x: x['displayName'].lower())
            
        except Exception as e:
            print(f"Error searching users: {str(e)}")
    
    return {"users": results}

@app.get("/profile/{user_id}", response_class=HTMLResponse)
async def user_profile(request: Request, user_id: str):
    """View another user's profile"""
    # Check if the profile user exists
    try:
        profile_user = auth.get_user(user_id)
    except:
        # If the user doesn't exist, redirect to home
        return RedirectResponse(url="/home", status_code=status.HTTP_303_SEE_OTHER)
    
    try:
        # Get profile user data
        profile_user_doc = db.collection('Users').document(user_id).get()
        if not profile_user_doc.exists:
            return RedirectResponse(url="/home", status_code=status.HTTP_303_SEE_OTHER)
        
        profile_user_data = profile_user_doc.to_dict()
        
        # Check if the current user follows this profile
        current_user_id = request.state.user.uid
        is_following = False
        
        if current_user_id != user_id:  # Don't check if viewing own profile
            follow_doc = db.collection('Users').document(current_user_id).collection('Following').document(user_id).get()
            is_following = follow_doc.exists
        
        # Fetch user's posts
        posts_ref = db.collection('Posts').where('userId', '==', user_id).order_by('createdAt', direction=firestore.Query.DESCENDING).limit(30)
        posts = []
        
        for post in posts_ref.stream():
            post_data = post.to_dict()
            if 'postId' not in post_data:
                post_data['postId'] = post.id
            posts.append(post_data)
        
        # Count followers and following
        followers_count = 0
        following_count = 0
        
        followers_ref = db.collection('Users').document(user_id).collection('Followers')
        followers_count = len(list(followers_ref.limit(1000).stream()))
        
        following_ref = db.collection('Users').document(user_id).collection('Following')
        following_count = len(list(following_ref.limit(1000).stream()))
        
        # Add counts to user data
        profile_user_data['post_count'] = len(posts)
        profile_user_data['followers_count'] = followers_count
        profile_user_data['following_count'] = following_count
        
        # Render profile page
        return templates.TemplateResponse(
            "user_profile.html", 
            {
                "request": request,
                "user_data": request.state.user_data,  # Current logged-in user data
                "profile_user": profile_user_data,     # Profile being viewed
                "is_following": is_following,
                "posts": posts
            }
        )
    except Exception as e:
        print(f"Error viewing user profile: {str(e)}")
        # If there's an error, redirect to home
        return RedirectResponse(url="/home?error=Could not load profile", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/follow/{user_id}")
async def follow_user(request: Request, user_id: str):
    """Follow a user"""
    current_user_id = request.state.user.uid
    
    # Don't allow following yourself
    if current_user_id == user_id:
        return {"success": False, "message": "You cannot follow yourself"}
    
    try:
        # Check if the target user exists
        try:
            target_user = auth.get_user(user_id)
        except:
            return {"success": False, "message": "User not found"}
        
        # Check if already following
        follow_doc = db.collection('Users').document(current_user_id).collection('Following').document(user_id).get()
        if follow_doc.exists:
            return {"success": False, "message": "Already following this user"}
        
        # Get current user data for the follower record
        current_user_data = request.state.user_data
        
        # Create following record in current user's document
        db.collection('Users').document(current_user_id).collection('Following').document(user_id).set({
            'userId': user_id,
            'createdAt': firestore.SERVER_TIMESTAMP
        })
        
        # Create follower record in target user's document
        db.collection('Users').document(user_id).collection('Followers').document(current_user_id).set({
            'userId': current_user_id,
            'username': current_user_data.get('username', ''),
            'displayName': current_user_data.get('displayName', ''),
            'photoURL': current_user_data.get('photoURL', None),
            'createdAt': firestore.SERVER_TIMESTAMP
        })
        
        return {"success": True, "message": "Successfully followed user"}
        
    except Exception as e:
        print(f"Error following user: {e}")
        return {"success": False, "message": f"An error occurred: {str(e)}"}

@app.post("/unfollow/{user_id}")
async def unfollow_user(request: Request, user_id: str):
    """Unfollow a user"""
    current_user_id = request.state.user.uid
    
    # Don't allow unfollowing yourself
    if current_user_id == user_id:
        return {"success": False, "message": "You cannot unfollow yourself"}
    
    try:
        # Check if actually following the user
        follow_doc = db.collection('Users').document(current_user_id).collection('Following').document(user_id).get()
        if not follow_doc.exists:
            return {"success": False, "message": "You are not following this user"}
        
        # Remove from current user's following collection
        db.collection('Users').document(current_user_id).collection('Following').document(user_id).delete()
        
        # Remove from target user's followers collection
        db.collection('Users').document(user_id).collection('Followers').document(current_user_id).delete()
        
        return {"success": True, "message": "Successfully unfollowed user"}
        
    except Exception as e:
        print(f"Error unfollowing user: {e}")
        return {"success": False, "message": f"An error occurred: {str(e)}"}

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
