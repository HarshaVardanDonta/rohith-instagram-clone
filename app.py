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
    """Render home page with feed posts"""
    # User data is now available in request.state
    user_id = request.state.user.uid
    
    try:
        # Fetch recent posts for the feed, ordered by creation time (most recent first)
        # In a real app, you'd fetch posts from users that the current user follows
        # For demo purposes, we'll just get the most recent posts from all users
        posts_ref = db.collection('Posts').order_by('createdAt', direction=firestore.Query.DESCENDING).limit(10)
        feed_posts = []
        
        # Get the posts and format them for the template
        for post in posts_ref.stream():
            post_data = post.to_dict()
            # Add post ID if not present in the data
            if 'postId' not in post_data:
                post_data['postId'] = post.id
            feed_posts.append(post_data)
            
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

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
