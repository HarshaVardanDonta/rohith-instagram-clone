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

load_dotenv()

async def squash_image(file_content, content_type, max_size=(1024, 1024), quality=85):
    try:
        img = Image.open(io.BytesIO(file_content))
        
        if content_type == "image/jpeg" or content_type == "image/jpg":
            fmt = "JPEG"
            new_type = "image/jpeg"
        elif content_type == "image/png":
            fmt = "PNG" 
            new_type = "image/png"
        elif content_type == "image/gif":
            fmt = "GIF"
            new_type = "image/gif"
        elif content_type == "image/webp":
            fmt = "WEBP"
            new_type = "image/webp"
        else:
            fmt = "JPEG"
            new_type = "image/jpeg"
        
        if img.width > max_size[0] or img.height > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        output = io.BytesIO()
        
        if fmt == "PNG":
            img.save(output, format=fmt, optimize=True)
        elif fmt == "GIF":
            img.save(output, format=fmt)
        else:
            img.save(output, format=fmt, quality=quality, optimize=True)
        
        output.seek(0)
        return output.getvalue(), new_type
    except Exception as e:
        print(f"Image compression error: {str(e)}")
        return file_content, content_type

firebase_cred_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
gcs_cred_path = os.getenv('GOOGLE_CLOUD_SERVICE_ACCOUNT_PATH')
bucket_name = os.getenv('GOOGLE_CLOUD_STORAGE_BUCKET')

try:
    if firebase_cred_path and os.path.exists(firebase_cred_path):
        cred = credentials.Certificate(firebase_cred_path)
        firebase_admin.initialize_app(cred, {
            'projectId': os.getenv('FIREBASE_PROJECT_ID'),
        })
    else:
        firebase_admin.initialize_app(options={
            'projectId': os.getenv('FIREBASE_PROJECT_ID'),
        })
except ValueError as e:
    print(f"Firebase init note: {e}") 
db_client = firestore.client()

gcs_client = None
try:
    if gcs_cred_path and os.path.exists(gcs_cred_path):
        gcs_client = gcs.Client.from_service_account_json(gcs_cred_path)
        print("GCS client ready")
    else:
        print("Warning: GCS account path not found")
        gcs_client = gcs.Client()
except Exception as e:
    print(f"GCS client error: {e}")

app = FastAPI(title="Social")

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        public_urls = ['/login', '/signup', '/forgot-password', '/static', '/favicon.ico']
        
        is_public = any(request.url.path.startswith(path) for path in public_urls)
        
        if not is_public:
            user_id = request.cookies.get("user_id")
            token = request.cookies.get("auth_token")
            
            token_expiry = request.cookies.get("token_expiry")
            is_token_valid = False
            
            if user_id and token and token_expiry:
                try:
                    expiry_time = datetime.fromtimestamp(float(token_expiry))
                    if expiry_time > datetime.now():
                        is_token_valid = True
                    else:
                        response = RedirectResponse(url="/login?message=Session expired. Please log in again.")
                        response.delete_cookie("user_id")
                        response.delete_cookie("auth_token")
                        response.delete_cookie("token_expiry")
                        return response
                except:
                    pass
            
            if not user_id or not is_token_valid:
                return RedirectResponse(url="/login")
            
            try:
                user = auth.get_user(user_id)
                request.state.user = user
                
                user_doc = db_client.collection('Users').document(user_id).get()
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
                print(f"Error fetching user data: {e}")
                response = RedirectResponse(url="/login")
                response.delete_cookie("user_id")
                response.delete_cookie("auth_token")
                response.delete_cookie("token_expiry")
                return response
        
        response = await call_next(request)
        return response

app.add_middleware(AuthMiddleware)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
security = HTTPBasic()

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    user_id = request.cookies.get("user_id")
    if user_id:
        return RedirectResponse(url="/home")
    return RedirectResponse(url="/login")

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup")
async def signup(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    username: str = Form(...)
):
    try:
        username_query = db_client.collection('Users').where('username', '==', username).limit(1).get()
        if len(username_query) > 0:
            return templates.TemplateResponse(
                "signup.html", 
                {"request": request, "error": "Username already taken. Please choose a different username."}
            )

        new_user = auth.create_user(
            email=email,
            password=password,
            display_name=full_name
        )
        
        try:
            users_ref = db_client.collection('Users')
            users_ref.document(new_user.uid).set({
                'uid': new_user.uid,
                'email': email,
                'displayName': full_name,
                'username': username,
                'createdAt': firestore.SERVER_TIMESTAMP,
                'lastLogin': firestore.SERVER_TIMESTAMP,
                'photoURL': None,
            })
            print(f"User data stored for: {new_user.uid}")
        except Exception as db_error:
            print(f"Error saving user data: {db_error}")
        
        return RedirectResponse(url="/login?message=Account created! Please log in.", status_code=status.HTTP_303_SEE_OTHER)
    
    except firebase_admin.exceptions.FirebaseError as e:
        error_message = "An error occurred during signup. Please try again."
        error_code = getattr(e, 'code', None)
        
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
        print(f"Unexpected error during signup: {str(e)}")
        
        return templates.TemplateResponse(
            "signup.html", 
            {"request": request, "error": "An unexpected error occurred. Please try again later."}
        )

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, message: str = None):
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
    try:
        try:
            user = auth.get_user_by_email(email)
            
            my_token = str(uuid.uuid4())
            token_expiry = datetime.now() + timedelta(days=7)
            
            try:
                users_ref = db_client.collection('Users')
                users_ref.document(user.uid).set({
                    'uid': user.uid,
                    'email': user.email,
                    'displayName': user.display_name,
                    'lastLogin': firestore.SERVER_TIMESTAMP,
                    'photoURL': user.photo_url if user.photo_url else None,
                    'currentToken': my_token,
                    'tokenExpiry': token_expiry.timestamp()
                }, merge=True)
                print(f"User login updated: {user.uid}")
            except Exception as db_error:
                print(f"Error updating user data: {db_error}")
            
            response = RedirectResponse(url="/home", status_code=status.HTTP_303_SEE_OTHER)
            
            # cookies for auth
            response.set_cookie(
                key="user_id", 
                value=user.uid,
                httponly=True,
                max_age=7 * 24 * 3600,
                secure=False
            )
            response.set_cookie(
                key="auth_token", 
                value=my_token,
                httponly=True,
                max_age=7 * 24 * 3600,
                secure=False
            )
            response.set_cookie(
                key="token_expiry", 
                value=str(token_expiry.timestamp()),
                httponly=True,
                max_age=7 * 24 * 3600,
                secure=False
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
    user_id = request.state.user.uid
    
    try:
        feed_stuff = []
        
        following_ref = db_client.collection('Users').document(user_id).collection('Following')
        my_people = [user_id]
        
        for follow_doc in following_ref.stream():
            follow_data = follow_doc.to_dict()
            if 'userId' in follow_data:
                my_people.append(follow_data['userId'])
        
        for followed_user_id in my_people:
            user_posts_ref = db_client.collection('Posts').where('userId', '==', followed_user_id).order_by('createdAt', direction=firestore.Query.DESCENDING)
            
            for post in user_posts_ref.stream():
                post_data = post.to_dict()
                if 'postId' not in post_data:
                    post_data['postId'] = post.id
                
                try:
                    comments_ref = db_client.collection('Posts').document(post_data['postId']).collection('Comments').order_by('createdAt', direction=firestore.Query.DESCENDING).limit(5)
                    post_comments = []
                    for comment_doc in comments_ref.stream():
                        comment_data = comment_doc.to_dict()
                        post_comments.append(comment_data)
                    
                    post_data['top_comments'] = post_comments
                except Exception as e:
                    print(f"Error getting comments for {post_data['postId']}: {str(e)}")
                    post_data['top_comments'] = []
                
                feed_stuff.append(post_data)
        
        feed_stuff.sort(key=lambda x: x.get('createdAt', 0), reverse=True)
        
        feed_stuff = feed_stuff[:50]
            
        return templates.TemplateResponse("home.html", {
            "request": request, 
            "user": request.state.user,
            "user_data": request.state.user_data,
            "feed_posts": feed_stuff
        })
    except Exception as e:
        print(f"Error getting feed: {str(e)}")
        return templates.TemplateResponse("home.html", {
            "request": request, 
            "user": request.state.user,
            "user_data": request.state.user_data,
            "feed_posts": []
        })

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("user_id")
    response.delete_cookie("auth_token")
    response.delete_cookie("token_expiry")
    return response

@app.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse(
        "forgot_password.html", 
        {"request": request}
    )

@app.post("/forgot-password")
async def forgot_password(
    request: Request,
    email: str = Form(...)
):
    try:
        reset_link = auth.generate_password_reset_link(email)
        
        return templates.TemplateResponse(
            "forgot_password.html", 
            {
                "request": request, 
                "message": "Password reset link has been sent to your email.",
                "reset_link": reset_link
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
    user_id = request.state.user.uid
    
    try:
        posts_ref = db_client.collection('Posts').where('userId', '==', user_id).order_by('createdAt', direction=firestore.Query.DESCENDING).limit(30)
        my_posts = []
        
        for post in posts_ref.stream():
            post_data = post.to_dict()
            if 'postId' not in post_data:
                post_data['postId'] = post.id
            my_posts.append(post_data)
        
        post_count = len(my_posts)
        
        user_data = request.state.user_data
        user_data['post_count'] = post_count
        
        return templates.TemplateResponse(
            "profile.html", 
            {
                "request": request, 
                "user": request.state.user,
                "user_data": user_data,
                "posts": my_posts
            }
        )
    except Exception as e:
        print(f"Error getting posts: {str(e)}")
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
    user_id = request.cookies.get("user_id")
    
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    try:
        user = auth.get_user(user_id)
        
        user_doc = db_client.collection('Users').document(user_id).get()
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
    user_id = request.cookies.get("user_id")
    
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    try:
        user = auth.get_user(user_id)
        
        profile_updates = {
            'username': username,
            'displayName': full_name
        }
        
        if profile_photo and profile_photo.filename:
            try:
                file_extension = os.path.splitext(profile_photo.filename)[1]
                file_name = f"profile_photos/{user_id}/{uuid.uuid4()}{file_extension}"
                
                file_content = await profile_photo.read()
                
                compressed_content, content_type = await squash_image(file_content, profile_photo.content_type)
                
                blob = gcs_client.bucket(bucket_name).blob(file_name)
                blob.upload_from_string(
                    compressed_content,
                    content_type=content_type
                )
                
                blob.make_public()
                
                image_url = blob.public_url
                
                profile_updates['photoURL'] = image_url
                
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
                        "user_data": profile_updates,
                        "error": "Failed to upload profile photo. Please try again."
                    }
                )
        else:
            auth.update_user(
                user_id,
                display_name=full_name
            )
        
        db_client.collection('Users').document(user_id).update(profile_updates)
        
        return RedirectResponse(url="/profile?message=Profile updated successfully", status_code=status.HTTP_303_SEE_OTHER)
        
    except Exception as e:
        print(f"Profile update error: {str(e)}")
        user_doc = db_client.collection('Users').document(user_id).get()
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
    user_id = request.state.user.uid
    
    try:
        if not image or not image.filename:
            return templates.TemplateResponse(
                "create_post.html", 
                {
                    "request": request, 
                    "error": "Image file is required"
                }
            )
            
        allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
        if image.content_type not in allowed_types:
            return templates.TemplateResponse(
                "create_post.html", 
                {
                    "request": request, 
                    "error": "Only JPEG, PNG, GIF, and WebP images are allowed"
                }
            )
        
        post_id = str(uuid.uuid4())
        file_extension = os.path.splitext(image.filename)[1]
        file_name = f"posts/{user_id}/{post_id}{file_extension}"
        
        file_content = await image.read()
        
        compressed_content, content_type = await squash_image(file_content, image.content_type)
        
        blob = gcs_client.bucket(bucket_name).blob(file_name)
        blob.upload_from_string(
            compressed_content,
            content_type=content_type
        )
        
        blob.make_public()
        
        image_url = blob.public_url
        
        print(f"Image uploaded: {file_name}")
        
        post_stuff = {
            'postId': post_id,
            'userId': user_id,
            'description': description,
            'imageUrl': image_url,
            'imagePath': file_name,
            'createdAt': firestore.SERVER_TIMESTAMP,
            'likes': 0,
            'comments': 0
        }
        
        user_data = request.state.user_data
        post_stuff['username'] = user_data.get('username', '')
        post_stuff['userPhotoURL'] = user_data.get('photoURL', '')
        
        db_client.collection('Posts').document(post_id).set(post_stuff)
        
        db_client.collection('Users').document(user_id).collection('Posts').document(post_id).set({
            'postId': post_id,
            'createdAt': firestore.SERVER_TIMESTAMP
        })
        
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
    try:
        try:
            profile_user = auth.get_user(user_id)
        except:
            return RedirectResponse(url="/home", status_code=status.HTTP_303_SEE_OTHER)
        
        followers_ref = db_client.collection('Users').document(user_id).collection('Followers')
        followers_query = followers_ref.order_by('createdAt', direction=firestore.Query.DESCENDING)
        
        fan_list = []
        for doc in followers_query.stream():
            follower_data = doc.to_dict()
            if 'userId' in follower_data:
                follower_user_doc = db_client.collection('Users').document(follower_data['userId']).get()
                if follower_user_doc.exists:
                    follower_user = follower_user_doc.to_dict()
                    fan_list.append({
                        'uid': follower_data['userId'],
                        'username': follower_user.get('username', ''),
                        'displayName': follower_user.get('displayName', ''),
                        'photoURL': follower_user.get('photoURL', None)
                    })
        
        return templates.TemplateResponse("followers.html", {
            "request": request,
            "user_data": request.state.user_data,
            "profile_user_id": user_id,
            "followers": fan_list
        })
        
    except Exception as e:
        print(f"Error getting followers: {e}")
        return templates.TemplateResponse("followers.html", {
            "request": request,
            "user_data": request.state.user_data,
            "profile_user_id": user_id,
            "followers": []
        })

@app.get("/following/{user_id}", response_class=HTMLResponse)
async def following_page(request: Request, user_id: str):
    try:
        try:
            profile_user = auth.get_user(user_id)
        except:
            return RedirectResponse(url="/home", status_code=status.HTTP_303_SEE_OTHER)
        
        following_ref = db_client.collection('Users').document(user_id).collection('Following')
        following_query = following_ref.order_by('createdAt', direction=firestore.Query.DESCENDING)
        
        idol_list = []
        for doc in following_query.stream():
            following_data = doc.to_dict()
            if 'userId' in following_data:
                followed_user_doc = db_client.collection('Users').document(following_data['userId']).get()
                if followed_user_doc.exists:
                    followed_user = followed_user_doc.to_dict()
                    idol_list.append({
                        'uid': following_data['userId'],
                        'username': followed_user.get('username', ''),
                        'displayName': followed_user.get('displayName', ''),
                        'photoURL': followed_user.get('photoURL', None)
                    })
        
        return templates.TemplateResponse("following.html", {
            "request": request,
            "user_data": request.state.user_data,
            "profile_user_id": user_id,
            "following": idol_list
        })
        
    except Exception as e:
        print(f"Error getting following list: {e}")
        return templates.TemplateResponse("following.html", {
            "request": request,
            "user_data": request.state.user_data,
            "profile_user_id": user_id,
            "following": []
        })

@app.get("/search")
async def search_users(request: Request, query: str = None):
    results = []
    
    if query and query.strip():
        try:
            query = query.strip().lower()
            
            users_ref = db_client.collection('Users').limit(100).stream()
            
            for doc in users_ref:
                user_data = doc.to_dict()
                display_name = user_data.get('displayName', '').lower()
                
                if display_name.startswith(query):
                    results.append({
                        'uid': user_data.get('uid'),
                        'username': user_data.get('username'),
                        'displayName': user_data.get('displayName'),
                        'photoURL': user_data.get('photoURL')
                    })
            
            results.sort(key=lambda x: x['displayName'].lower())
            
        except Exception as e:
            print(f"Search error: {str(e)}")
    
    return {"users": results}

@app.get("/profile/{user_id}", response_class=HTMLResponse)
async def user_profile(request: Request, user_id: str):
    try:
        profile_user = auth.get_user(user_id)
    except:
        return RedirectResponse(url="/home", status_code=status.HTTP_303_SEE_OTHER)
    
    try:
        profile_user_doc = db_client.collection('Users').document(user_id).get()
        if not profile_user_doc.exists:
            return RedirectResponse(url="/home", status_code=status.HTTP_303_SEE_OTHER)
        
        profile_user_data = profile_user_doc.to_dict()
        
        current_user_id = request.state.user.uid
        am_i_following = False
        
        if current_user_id != user_id:  # no need to check for self
            follow_doc = db_client.collection('Users').document(current_user_id).collection('Following').document(user_id).get()
            am_i_following = follow_doc.exists
        
        posts_ref = db_client.collection('Posts').where('userId', '==', user_id).order_by('createdAt', direction=firestore.Query.DESCENDING).limit(30)
        user_posts = []
        
        for post in posts_ref.stream():
            post_data = post.to_dict()
            if 'postId' not in post_data:
                post_data['postId'] = post.id
            user_posts.append(post_data)
        
        followers_count = 0
        following_count = 0
        
        followers_ref = db_client.collection('Users').document(user_id).collection('Followers')
        followers_count = len(list(followers_ref.limit(1000).stream()))
        
        following_ref = db_client.collection('Users').document(user_id).collection('Following')
        following_count = len(list(following_ref.limit(1000).stream()))
        
        profile_user_data['post_count'] = len(user_posts)
        profile_user_data['followers_count'] = followers_count
        profile_user_data['following_count'] = following_count
        
        return templates.TemplateResponse(
            "user_profile.html", 
            {
                "request": request,
                "user_data": request.state.user_data,
                "profile_user": profile_user_data,
                "is_following": am_i_following,
                "posts": user_posts
            }
        )
    except Exception as e:
        print(f"Error viewing profile: {str(e)}")
        return RedirectResponse(url="/home?error=Could not load profile", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/follow/{user_id}")
async def follow_user(request: Request, user_id: str):
    current_user_id = request.state.user.uid
    
    if current_user_id == user_id:
        return {"success": False, "message": "You cannot follow yourself"}
    
    try:
        try:
            target_user = auth.get_user(user_id)
        except:
            return {"success": False, "message": "User not found"}
        
        follow_doc = db_client.collection('Users').document(current_user_id).collection('Following').document(user_id).get()
        if follow_doc.exists:
            return {"success": False, "message": "Already following this user"}
        
        current_user_data = request.state.user_data
        
        db_client.collection('Users').document(current_user_id).collection('Following').document(user_id).set({
            'userId': user_id,
            'createdAt': firestore.SERVER_TIMESTAMP
        })
        
        db_client.collection('Users').document(user_id).collection('Followers').document(current_user_id).set({
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
    current_user_id = request.state.user.uid
    
    if current_user_id == user_id:
        return {"success": False, "message": "You cannot unfollow yourself"}
    
    try:
        follow_doc = db_client.collection('Users').document(current_user_id).collection('Following').document(user_id).get()
        if not follow_doc.exists:
            return {"success": False, "message": "You are not following this user"}
        
        db_client.collection('Users').document(current_user_id).collection('Following').document(user_id).delete()
        
        db_client.collection('Users').document(user_id).collection('Followers').document(current_user_id).delete()
        
        return {"success": True, "message": "Successfully unfollowed user"}
        
    except Exception as e:
        print(f"Error unfollowing user: {e}") 
        return {"success": False, "message": f"An error occurred: {str(e)}"}

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
