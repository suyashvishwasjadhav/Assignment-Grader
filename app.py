# Copyright (c) 2024-2025 Suyash Vishwas Jadhav. All rights reserved.
# Project: EduEval - AI-Powered Automated Grading System
# Developer & Architect: Suyash Vishwas Jadhav

import os
import secrets
import smtplib
import requests
import json
import base64
import uuid
from datetime import datetime, timedelta, date
from flask import Flask, session, abort, redirect, request, render_template, url_for, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from email.mime.text import MIMEText
from oauthlib.oauth2 import WebApplicationClient
from functools import wraps
import google.generativeai as genai
import signal
from contextlib import contextmanager
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Allow OAuth over HTTP for local development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from extensions import db

# Initialize Flask app
app = Flask(__name__, 
    static_folder='static',
    template_folder='templates'
)

app.secret_key = secrets.token_hex(32)

# Configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "postgresql://postgres:1234@localhost/eddu")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Configure uploads
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# Create upload directory if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Initialize the extension with the app
db.init_app(app)

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "YOUR_GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "YOUR_GOOGLE_CLIENT_SECRET")
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

# Email configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'your-email@example.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'your-app-password')
app.config['RESET_TOKEN_EXPIRY'] = 3600  # 1 hour (in seconds)

# Configure Gemini API
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-pro')

# NLP setup
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
    print("SpaCy loaded successfully with en_core_web_sm model")
    USE_SPACY = True
except (ImportError, OSError) as e:
    print(f"SpaCy model not available: {e}")
    USE_SPACY = False

# OAuth client setup
client = WebApplicationClient(GOOGLE_CLIENT_ID)

# Store reset tokens (in a real app, store these in a database)
reset_tokens = {}

# Import models after app and db are defined
with app.app_context():
    from models import User, Organization, Teacher, Assignment, Question, Submission, QuestionResponse, ChatMessage
    
    # Create database tables
    db.create_all()
    
# Add a global context processor to make current year available to all templates
@app.context_processor
def inject_now():
    return {'current_year': datetime.now().year}

@app.route('/set-theme', methods=['POST'])
def set_theme():
    data = request.json
    theme = data.get('theme', 'light')
    
    if 'user_id' in session:
        user_id = session.get('user_id')
        user = User.query.get(user_id)
        if user:
            user.theme = theme
            db.session.commit()
    
    session['theme'] = theme
    return jsonify({'success': True})

# Timeout Exception
class TimeoutException(Exception): pass

@contextmanager
def time_limit(seconds):
    def signal_handler(signum, frame):
        raise TimeoutException("Timed out!")
    signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)

# Helper function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Authentication decorators
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login to access this page", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login to access this page", "warning")
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash("You don't have permission to access this page", "warning")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return wrapper

def student_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login to access this page", "warning")
            return redirect(url_for('login'))
        if session.get('role') != 'student':
            flash("You don't have permission to access this page", "warning")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return wrapper

# Email functions
def send_email(to_email, subject, body):
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = app.config['MAIL_USERNAME']
    msg['To'] = to_email
    
    server = smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT'])
    server.starttls()
    server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
    server.send_message(msg)
    server.quit()

def send_welcome_email(email, username):
    subject = "Welcome to EduEval!"
    body = f"""
    Hello {username},
    
    Welcome to EduEval! Your account has been successfully created.
    
    You can now login and start using our platform.
    
    Best regards,
    The EduEval Team
    """
    send_email(email, subject, body)

def send_login_notification(email, username, request):
    # Get current time in different formats
    login_time = datetime.now()
    formatted_date = login_time.strftime('%A, %B %d, %Y')
    formatted_time = login_time.strftime('%H:%M:%S %Z')
    
    # Get detailed browser and OS info
    browser = request.user_agent.browser or "Unknown"
    browser_version = request.user_agent.version or "Unknown"
    platform = request.user_agent.platform or "Unknown"
    os = request.user_agent.platform or "Unknown"
    device = "Mobile" if request.user_agent.platform in ['android', 'iphone', 'ipad'] else "Desktop/Laptop"
    
    # Get IP information
    ip = request.remote_addr
    
    subject = "Security Alert: New Login to Your EduEval Account"
    body = f"""
    Hello {username},
    
    We detected a new login to your EduEval account with the following details:
    
    📅 Date: {formatted_date}
    ⏰ Time: {formatted_time}
    🌐 IP Address: {ip}
    
    📱 Device Information:
    • Device Type: {device}
    • Operating System: {os}
    • Browser: {browser} {browser_version}
    
    If this was you, no action is needed. 
    
    ⚠️ If you did not login at this time, please:
    1. Reset your password immediately by clicking the link below
    2. Contact support if you need assistance
    
    {url_for('forgot_password', _external=True)}
    
    Stay secure,
    The EduEval Team
    """
    send_email(email, subject, body)

def send_reset_token(email, token):
    subject = "Password Reset Request"
    reset_url = url_for('reset_password', token=token, _external=True)
    body = f"""
    Hello,
    
    You requested a password reset for your EduEval account.
    Please follow this link to reset your password:
    
    {reset_url}
    
    This link will expire in 1 hour. If you didn't request this reset, please ignore this email.
    
    Best regards,
    The EduEval Team
    """
    send_email(email, subject, body)

# OCR and Text Processing Functions
def extract_text_from_image(image_path):
    try:
        # Using Apple Vision, Quartz, and Cocoa for OCR (macOS specific)
        print(f"Attempting to extract text from image: {image_path}")
        
        # For macOS implementation using Vision framework
        import Vision
        import Quartz
        from Cocoa import NSURL
        
        image_url = NSURL.fileURLWithPath_(image_path)
        ci_image = Quartz.CIImage.imageWithContentsOfURL_(image_url)
        if ci_image is None:
            print("Error: Could not load image.")
            return None
            
        request_handler = Vision.VNImageRequestHandler.alloc().initWithCIImage_options_(ci_image, None)
        request = Vision.VNRecognizeTextRequest.alloc().init()
        success, error = request_handler.performRequests_error_([request], None)
        
        if not success:
            print("Error performing OCR:", error)
            return None
            
        recognized_text = []
        for result in request.results():
            recognized_text.append(result.topCandidates_(1)[0].string())
            
        return "\n".join(recognized_text)
    except ImportError:
        print("macOS Vision, Quartz, or Cocoa frameworks not available. OCR will not function.")
        return f"[OCR unavailable - macOS frameworks required] {os.path.basename(image_path)}"
    except Exception as e:
        print(f"Error extracting text from image: {e}")
        return None

def preprocess_text(text):
    if not text:
        return ""
    
    if USE_SPACY:
        try:
            doc = nlp(text.lower())  
            return " ".join([token.lemma_ for token in doc if not token.is_stop and not token.is_punct])
        except Exception as e:
            print(f"Error in spaCy processing: {e}")
    
    # Fallback simple preprocessing if spaCy is not available
    # Remove punctuation and lowercase
    import re
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    
    # Remove common stop words (simplified version)
    stop_words = {'a', 'an', 'the', 'and', 'or', 'but', 'if', 'then', 'than', 'so', 'too'}
    words = text.split()
    filtered_words = [word for word in words if word not in stop_words]
    
    return ' '.join(filtered_words)

def calculate_similarity_nlp(student_answer, correct_answer, timeout_seconds=10):
    if not student_answer or not correct_answer:
        return 0.0
        
    # Keep original text for backup comparison
    original_student = student_answer
    original_correct = correct_answer
    
    # Check for exact matches before any preprocessing
    if original_student.strip().lower() == original_correct.strip().lower():
        return 100.0
        
    # Try preprocessing
    student_answer = preprocess_text(student_answer)
    correct_answer = preprocess_text(correct_answer)
    
    # If preprocessing removes too much, use original text
    if len(student_answer.split()) < 3 or len(correct_answer.split()) < 3:
        student_answer = original_student.lower()
        correct_answer = original_correct.lower()
    
    if not student_answer or not correct_answer:
        return 0.0
    
    # Check if answers are identical after preprocessing
    if student_answer == correct_answer:
        return 100.0
    
    # Check for significant overlap
    student_words = set(student_answer.split())
    correct_words = set(correct_answer.split())
    
    # Check for high word overlap (more than 90% of words match)
    if len(student_words) > 0 and len(correct_words) > 0:
        if len(student_words.intersection(correct_words)) / len(correct_words) > 0.9:
            return 95.0
    
    # Calculate jaccard similarity as a fallback
    intersection = len(student_words.intersection(correct_words))
    union = len(student_words.union(correct_words))
    
    if union == 0:
        return 0.0
        
    jaccard_sim = (intersection / union) * 100
    
    # If jaccard similarity is very high, boost the score
    if jaccard_sim > 85:
        return 92.0
    
    # Calculate word order similarity (bigram overlap)
    student_bigrams = set(zip(student_answer.split()[:-1], student_answer.split()[1:]))
    correct_bigrams = set(zip(correct_answer.split()[:-1], correct_answer.split()[1:]))
    
    bigram_intersection = len(student_bigrams.intersection(correct_bigrams))
    bigram_union = len(student_bigrams.union(correct_bigrams))
    
    bigram_sim = 0.0
    if bigram_union > 0:
        bigram_sim = (bigram_intersection / bigram_union) * 100
        
    # If bigram similarity is very high, boost the score
    if bigram_sim > 80:
        return 90.0
    
    # Only use TF-IDF if there are enough common words
    if len(student_words.intersection(correct_words)) >= 2:
        try:
            with time_limit(timeout_seconds):
                vectorizer = TfidfVectorizer(min_df=0, max_df=1.0)
                vectors = vectorizer.fit_transform([student_answer, correct_answer])
                
                if vectors.shape[1] == 0:
                    # Enhanced fallback - use weighted average of jaccard and bigram similarities
                    base_score = (jaccard_sim * 0.7) + (bigram_sim * 0.3)
                    # Boost slightly low scores if there's good word overlap
                    if intersection / len(correct_words) > 0.7:
                        return max(base_score, 85.0)
                    return base_score
                    
                cosine_sim = cosine_similarity(vectors[0], vectors[1])[0][0]
                if np.isnan(cosine_sim):
                    # Enhanced fallback - use weighted average of jaccard and bigram similarities
                    return (jaccard_sim * 0.7) + (bigram_sim * 0.3)
                
                # Calculate final score using a weighted combination of all metrics
                cosine_score = cosine_sim * 100
                
                # Boost the score for high cosine similarity
                if cosine_score > 80:
                    return min(cosine_score + 10, 100.0)
                    
                final_score = (cosine_score * 0.6) + (jaccard_sim * 0.3) + (bigram_sim * 0.1)
                
                # Final check to avoid underscoring good answers
                if intersection / len(correct_words) > 0.8:
                    return max(final_score, 90.0)
                    
                return round(final_score, 2)
        except (TimeoutException, Exception) as e:
            print(f"Error or timeout in similarity calculation: {e}")
            # Enhanced fallback - use weighted average of jaccard and bigram similarities
            base_score = (jaccard_sim * 0.7) + (bigram_sim * 0.3)
            # Boost slightly low scores if there's good word overlap
            if intersection / len(correct_words) > 0.7:
                return max(base_score, 85.0)
            return base_score
    
    # Enhanced fallback - use weighted average of jaccard and bigram similarities
    base_score = (jaccard_sim * 0.7) + (bigram_sim * 0.3)
    # Boost slightly low scores if there's good word overlap
    if intersection / len(correct_words) > 0.7:
        return max(base_score, 85.0)
    return base_score

def evaluate_with_gemini(question, student_answer):
    try:
        prompt = f"""
        Question: {question}
        Student Answer: {student_answer}
        
        Act as an expert educational evaluator. Evaluate the student's answer based on:
        1. Relevance: How directly it addresses the question (50%)
        2. Accuracy: Factual correctness of the answer (35%)
        3. Completeness: How thoroughly it covers the expected content (15%)
        
        Evaluation criteria:
        - An excellent answer (90-100) directly addresses the question with accurate information and comprehensive content
        - A good answer (70-89) addresses the question with mostly accurate information but may lack some details
        - A fair answer (50-69) partially addresses the question with some inaccuracies or significant gaps
        - A poor answer (0-49) fails to address the question, contains major inaccuracies, or is severely lacking in content
        
        After analysis, provide:
        1. A relevance score from 0-100 considering all the above factors
        2. Brief, specific feedback on what was good and what was missing or incorrect
        
        Format your response as a JSON with 'relevance_score' and 'feedback' keys.
        """
        
        response = model.generate_content(prompt)
        response_text = response.text
        
        # Try to extract JSON from the response
        try:
            # Look for JSON patterns in the response
            if '{' in response_text and '}' in response_text:
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)
            else:
                # If no JSON found, make a simple estimate
                result = {
                    "relevance_score": 50.0,
                    "feedback": "Could not properly evaluate the answer. Please review manually."
                }
            
            # Ensure feedback is a string
            if isinstance(result.get("feedback"), dict):
                result["feedback"] = str(result["feedback"])
            elif "feedback" not in result:
                result["feedback"] = "No feedback provided."
                
            # Ensure relevance_score is a number
            if not isinstance(result.get("relevance_score"), (int, float)):
                if "relevance_score" in result:
                    try:
                        result["relevance_score"] = float(result["relevance_score"])
                    except (ValueError, TypeError):
                        result["relevance_score"] = 50.0
                else:
                    result["relevance_score"] = 50.0
                
            return result
        except json.JSONDecodeError:
            # If parsing fails, create a default response
            return {
                "relevance_score": 50.0,
                "feedback": "Failed to parse evaluation. Please review the answer manually."
            }
    except Exception as e:
        print(f"Error evaluating with Gemini: {e}")
        return {
            "relevance_score": 0.0,
            "feedback": f"Error processing with AI: {str(e)}"
        }

def evaluate_grammar_with_gemini(text):
    try:
        prompt = f"""
        Act as an expert language teacher evaluating a student's writing. Analyze the following text for:
        
        1. Grammar & Syntax (40%): Correctness of sentence structure, verb tenses, subject-verb agreement
        2. Coherence & Flow (30%): Logical connection between ideas, appropriate transitions, clarity of thought
        3. Vocabulary Usage (20%): Appropriate word choice, lexical variety, precision of expression
        4. Mechanics (10%): Punctuation, capitalization, spelling
        
        Evaluation criteria:
        - Excellent (90-100): Nearly error-free with sophisticated language use and clear organization
        - Good (75-89): Few errors that don't impede understanding, clear structure, good vocabulary
        - Satisfactory (60-74): Some errors but generally understandable, basic structure, adequate vocabulary
        - Needs Improvement (0-59): Frequent errors that impede understanding, disorganized, limited vocabulary
        
        Text to evaluate: "{text}"
        
        After careful analysis, provide:
        1. A grammar score from 0-100 considering all the above factors
        2. Brief, constructive feedback highlighting strengths and areas for improvement
        
        Format your response as a JSON with 'grammar_score' and 'grammar_feedback' keys.
        """
        
        response = model.generate_content(prompt)
        response_text = response.text
        
        # Try to extract JSON from the response
        try:
            # Look for JSON patterns in the response
            if '{' in response_text and '}' in response_text:
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)
            else:
                # If no JSON found, make a simple estimate
                result = {
                    "grammar_score": 70.0,
                    "grammar_feedback": "Grammar evaluation unavailable."
                }
            
            # Ensure the score is a number
            if not isinstance(result.get("grammar_score"), (int, float)):
                if "grammar_score" in result:
                    try:
                        result["grammar_score"] = float(result["grammar_score"])
                    except (ValueError, TypeError):
                        result["grammar_score"] = 70.0
                else:
                    result["grammar_score"] = 70.0
                
            return result
        except json.JSONDecodeError:
            # If parsing fails, create a default response
            return {
                "grammar_score": 70.0,
                "grammar_feedback": "Grammar evaluation failed. Please review manually."
            }
    except Exception as e:
        print(f"Error evaluating grammar with Gemini: {e}")
        return {
            "grammar_score": 70.0,
            "grammar_feedback": f"Error processing grammar with AI: {str(e)}"
        }

# Routes
@app.route('/')
def index():
    return render_template("index.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/signup", methods=['GET', 'POST'])
def signup():
    if "user_id" in session:
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('student_dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        role = request.form.get('role', 'student')
        
        # Add validation for required fields
        if not username or not email or not password:
            flash('Username, email, and password are required fields', 'error')
            return redirect(url_for('signup'))
        
        # Validate passwords match
        if password != confirm_password:
            flash('Passwords do not match!', 'error')
            return redirect(url_for('signup'))
        
        # Check if user exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already registered!', 'error')
            return redirect(url_for('signup'))
        
        # Handle organization
        organization_id = None
        
        if role == 'admin':
            use_existing_org = request.form.get('use_existing_org') == 'on'
            if use_existing_org:
                org_name = request.form.get('existing_organization')
                if not org_name:
                    flash('Please select an organization', 'error')
                    return redirect(url_for('signup'))
                
                org = Organization.query.filter_by(name=org_name).first()
                if org:
                    organization_id = org.id
            else:
                org_name = request.form.get('organization_name')
                if not org_name:
                    flash('Organization name is required', 'error')
                    return redirect(url_for('signup'))
                
                new_org = Organization(name=org_name)
                db.session.add(new_org)
                db.session.commit()
                organization_id = new_org.id
        else:
            # Student must join an existing organization
            org_name = request.form.get('existing_organization')
            if not org_name:
                flash('Please select an organization', 'error')
                return redirect(url_for('signup'))
            
            org = Organization.query.filter_by(name=org_name).first()
            if org:
                organization_id = org.id
            else:
                flash('Selected organization does not exist', 'error')
                return redirect(url_for('signup'))
        
        # Double-check password is not None before hashing
        if not password:
            flash('Password is required', 'error')
            return redirect(url_for('signup'))
            
        # Create new user
        new_user = User(
            username=username,
            email=email,
            password=generate_password_hash(password),
            role=role,
            login_type='standard',
            organization_id=organization_id
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        # Create teacher record if admin
        if role == 'admin':
            new_teacher = Teacher(user_id=new_user.id)
            db.session.add(new_teacher)
            db.session.commit()

        try:
            send_welcome_email(email, username)
        except Exception as e:
            print(f"Failed to send welcome email: {str(e)}")
            flash("Registration successful, but we couldn't send a welcome email.", "warning")
        else:
            flash('Registration successful! Please login.', 'success')
        
        return redirect(url_for('login', role=role))
    
    # For GET request
    role = request.args.get('role', 'student')
    organizations = [org.name for org in Organization.query.all()]
    
    return render_template("signup.html", role=role, organizations=organizations)

@app.route("/login", methods=['GET', 'POST'])
def login():
    if "user_id" in session:
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('student_dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        
        # Find user
        user = User.query.filter_by(email=email).first()
        
        if user and user.password and check_password_hash(user.password, password):
            # Check if role matches
            if role and user.role != role:
                flash(f'This account is not registered as a {role}', 'error')
                return redirect(url_for('login', role=role))
            
            session['user_id'] = user.id
            session['username'] = user.username
            session['email'] = user.email
            session['role'] = user.role
            
            # Set theme preference
            session['theme'] = user.theme
            
            # Send login notification email
            try:
                send_login_notification(user.email, user.username, request)
            except Exception as e:
                print(f"Failed to send login notification: {str(e)}")
                # Continue with login process even if email fails
            
            flash('Login successful!', 'success')
            
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))
        
        flash('Invalid email or password', 'error')
        return redirect(url_for('login', role=role))
    
    # For GET request
    role = request.args.get('role', 'student')
    return render_template("login.html", role=role)

@app.route("/google-login")
def google_login():
    # Get Google provider configuration
    google_provider_cfg = requests.get(GOOGLE_DISCOVERY_URL).json()
    authorization_endpoint = google_provider_cfg["authorization_endpoint"]
    
    # Use the library to construct the request for Google login
    role = request.args.get('role', 'student')
    
    # Store role in session for later use
    session['oauth_role'] = role
    
    # Use the exact redirect URI that was configured in the Google Cloud Console
    # These are the authorized redirect URIs you've set up
    redirect_uri = "http://localhost:5000/auth/google/callback"
    
    # Generate request URI
    request_uri = client.prepare_request_uri(
        authorization_endpoint,
        redirect_uri=redirect_uri,
        scope=["openid", "email", "profile"],
    )
    
    return redirect(request_uri)

@app.route("/auth/google/callback")
def google_callback():
    # Get authorization code from the callback request
    code = request.args.get("code")
    
    # Get Google provider configuration
    google_provider_cfg = requests.get(GOOGLE_DISCOVERY_URL).json()
    token_endpoint = google_provider_cfg["token_endpoint"]
    
    # Prepare and send token request
    token_url, headers, body = client.prepare_token_request(
        token_endpoint,
        authorization_response=request.url,
        redirect_url=request.base_url,
        code=code
    )
    
    # Ensure we have the client credentials
    if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
        token_response = requests.post(
            token_url,
            headers=headers,
            data=body,
            auth=(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET)
        )
    else:
        # Fallback if credentials are not available
        flash("Google authentication is not properly configured.", "error")
        return redirect(url_for('login'))
    
    # Parse the token response
    client.parse_request_body_response(json.dumps(token_response.json()))
    
    # Get user info from Google
    userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]
    uri, headers, body = client.add_token(userinfo_endpoint)
    userinfo_response = requests.get(uri, headers=headers, data=body)
    
    # Verify user's email is verified by Google
    userinfo = userinfo_response.json()
    if not userinfo.get("email_verified"):
        flash("User email not verified by Google", "error")
        return redirect(url_for('login'))
    
    # Get user information
    google_id = userinfo["sub"]
    users_email = userinfo["email"]
    users_name = userinfo.get("given_name") or userinfo.get("name", "User")
    
    # Check if user exists in our database
    user = User.query.filter_by(email=users_email).first()
    
    # Get role from session
    role = session.pop('oauth_role', 'student')
    
    if user:
        # Check if role matches
        if role and user.role != role:
            flash(f'This Google account is not registered as a {role}', 'error')
            return redirect(url_for('login', role=role))
        
        # User exists, update Google ID if needed
        if user.login_type != 'google':
            user.login_type = 'google'
            db.session.commit()
        
        # Log the user in
        session['user_id'] = user.id
        session['username'] = user.username
        session['email'] = user.email
        session['role'] = user.role
        session['theme'] = user.theme
        
        # Send login notification email
        try:
            send_login_notification(user.email, user.username, request)
        except Exception as e:
            print(f"Failed to send login notification: {e}")
            # Continue with login process even if email fails
            
        flash('Login successful!', 'success')
        
        if user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('student_dashboard'))
    else:
        # User doesn't exist, we need to create a new account
        flash("Please complete registration with your Google account", "info")
        
        # Store Google info in session to use in the signup form
        session['oauth_email'] = users_email
        session['oauth_name'] = users_name
        session['oauth_id'] = google_id
        
        return redirect(url_for('signup', role=role))

@app.route("/forgot-password", methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        
        # Find user
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Generate a reset token
            token = secrets.token_urlsafe(32)
            
            # Store token with expiry time
            expiry = datetime.now() + timedelta(seconds=app.config['RESET_TOKEN_EXPIRY'])
            reset_tokens[token] = {'email': email, 'expiry': expiry}
            
            # Send token to user's email
            try:
                send_reset_token(email, token)
                flash('Password reset link sent to your email!', 'success')
            except Exception as e:
                print(f"Failed to send reset email: {str(e)}")
                flash('Failed to send reset email. Please try again later.', 'error')
        else:
            # Still show success to prevent email enumeration
            flash('If your email is registered, you will receive a password reset link.', 'info')
            
        return redirect(url_for('login'))
        
    return render_template("forgot_password.html")

@app.route("/reset-password/<token>", methods=['GET', 'POST'])
def reset_password(token):
    # Check if token exists and is valid
    if token not in reset_tokens:
        flash('Invalid or expired reset token.', 'error')
        return redirect(url_for('login'))
    
    token_data = reset_tokens[token]
    
    # Check if token has expired
    if datetime.now() > token_data['expiry']:
        # Remove expired token
        reset_tokens.pop(token)
        flash('Reset token has expired. Please request a new one.', 'error')
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not password:
            flash('Password is required', 'error')
            return redirect(url_for('reset_password', token=token))
            
        if password != confirm_password:
            flash('Passwords do not match!', 'error')
            return redirect(url_for('reset_password', token=token))
            
        # Update user password
        user = User.query.filter_by(email=token_data['email']).first()
        if user:
            user.password = generate_password_hash(password)
            db.session.commit()
            
            # Remove used token
            reset_tokens.pop(token)
            
            flash('Password has been reset successfully!', 'success')
            return redirect(url_for('login'))
        else:
            flash('User not found.', 'error')
            return redirect(url_for('login'))
    
    return render_template("reset_password.html", token=token)

@app.route("/logout")
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

# Admin routes
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    organization = Organization.query.get(user.organization_id)
    
    # Get assignments for this admin
    assignments = Assignment.query.filter_by(creator_id=user_id).all()
    
    # Get organization students
    students = User.query.filter_by(
        organization_id=user.organization_id, 
        role='student'
    ).all()
    
    # Get total submissions
    submission_count = db.session.query(Submission).\
        join(Assignment).\
        filter(Assignment.creator_id == user_id).\
        count()
    
    return render_template(
        "admin/dashboard.html", 
        user=user,
        organization=organization,
        assignments=assignments,
        student_count=len(students),
        submission_count=submission_count
    )
    
@app.route("/admin/toggle-scores/<int:assignment_id>", methods=['POST'])
@admin_required
def toggle_scores(assignment_id):
    user_id = session.get('user_id')
    
    # Get assignment
    assignment = Assignment.query.get_or_404(assignment_id)
    
    # Ensure admin owns this assignment
    if assignment.creator_id != user_id:
        flash("You don't have permission to modify this assignment", "error")
        return redirect(url_for('admin_dashboard'))
    
    # Toggle score visibility
    assignment.show_scores = not assignment.show_scores
    db.session.commit()
    
    # Show appropriate message
    if assignment.show_scores:
        flash(f"Scores for '{assignment.title}' are now visible to students", "success")
    else:
        flash(f"Scores for '{assignment.title}' are now hidden from students", "info")
        
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/create-assignment", methods=['GET', 'POST'])
@admin_required
def create_assignment():
    if request.method == 'POST':
        user_id = session.get('user_id')
        
        # Get assignment data
        title = request.form.get('title')
        deadline_str = request.form.get('deadline')
        show_scores = request.form.get('show_scores') == 'on'
        
        # Validate data
        if not title:
            flash('Title is required', 'error')
            return redirect(url_for('create_assignment'))
        
        # Create assignment
        new_assignment = Assignment(
            title=title,
            creator_id=user_id,
            deadline=datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M') if deadline_str else None,
            show_scores=show_scores
        )
        
        db.session.add(new_assignment)
        db.session.commit()
        
        flash('Assignment created successfully!', 'success')
        return redirect(url_for('edit_assignment', assignment_id=new_assignment.id))
    
    return render_template("admin/create_assignment.html")

@app.route("/admin/edit-assignment/<int:assignment_id>", methods=['GET', 'POST'])
@admin_required
def edit_assignment(assignment_id):
    user_id = session.get('user_id')
    
    # Get assignment
    assignment = Assignment.query.get_or_404(assignment_id)
    
    # Ensure admin owns this assignment
    if assignment.creator_id != user_id:
        flash("You don't have permission to edit this assignment", "error")
        return redirect(url_for('admin_dashboard'))
    
    # Get questions
    questions = Question.query.filter_by(assignment_id=assignment_id).all()
    
    if request.method == 'POST':
        # Update assignment
        assignment.title = request.form.get('title')
        deadline_str = request.form.get('deadline')
        assignment.deadline = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M') if deadline_str else None
        assignment.show_scores = request.form.get('show_scores') == 'on'
        
        db.session.commit()
        flash('Assignment updated successfully!', 'success')
        return redirect(url_for('edit_assignment', assignment_id=assignment_id))
    
    return render_template(
        "admin/create_assignment.html", 
        assignment=assignment,
        questions=questions,
        edit_mode=True
    )

@app.route("/admin/add-question/<int:assignment_id>", methods=['POST'])
@admin_required
def add_question(assignment_id):
    user_id = session.get('user_id')
    
    # Get assignment
    assignment = Assignment.query.get_or_404(assignment_id)
    
    # Ensure admin owns this assignment
    if assignment.creator_id != user_id:
        flash("You don't have permission to edit this assignment", "error")
        return redirect(url_for('admin_dashboard'))
    
    # Get question data
    question_text = request.form.get('question_text')
    evaluation_method = request.form.get('evaluation_method')
    answer_key = request.form.get('answer_key') if evaluation_method == 'answer_key' else None
    max_marks = request.form.get('max_marks')
    word_count = request.form.get('word_count')
    
    # Validate data
    if not question_text or not evaluation_method or not max_marks or not word_count:
        flash('All fields are required', 'error')
        return redirect(url_for('edit_assignment', assignment_id=assignment_id))
    
    if evaluation_method == 'answer_key' and not answer_key:
        flash('Answer key is required for answer key evaluation method', 'error')
        return redirect(url_for('edit_assignment', assignment_id=assignment_id))
    
    # Create question
    new_question = Question(
        assignment_id=assignment_id,
        question_text=question_text,
        evaluation_method=evaluation_method,
        answer_key=answer_key,
        max_marks=max_marks,
        word_count=word_count
    )
    
    db.session.add(new_question)
    db.session.commit()
    
    flash('Question added successfully!', 'success')
    return redirect(url_for('edit_assignment', assignment_id=assignment_id))

@app.route("/admin/delete-question/<int:question_id>", methods=['POST'])
@admin_required
def delete_question(question_id):
    user_id = session.get('user_id')
    
    # Get question
    question = Question.query.get_or_404(question_id)
    
    # Get assignment
    assignment = Assignment.query.get(question.assignment_id)
    
    # Ensure admin owns this assignment
    if assignment.creator_id != user_id:
        flash("You don't have permission to delete this question", "error")
        return redirect(url_for('admin_dashboard'))
    
    # Delete question
    db.session.delete(question)
    db.session.commit()
    
    flash('Question deleted successfully!', 'success')
    return redirect(url_for('edit_assignment', assignment_id=assignment.id))

@app.route("/admin/students")
@admin_required
def admin_students():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    # Get organization students
    students = User.query.filter_by(
        organization_id=user.organization_id, 
        role='student'
    ).all()
    
    return render_template(
        "admin/students.html", 
        students=students
    )

@app.route("/admin/admins")
@admin_required
def admin_admins():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    # Get organization admins
    admins = User.query.filter_by(
        organization_id=user.organization_id, 
        role='admin'
    ).all()
    
    return render_template(
        "admin/students.html", 
        students=admins,
        is_admin_list=True
    )

@app.route("/admin/submissions/<int:assignment_id>")
@admin_required
def view_submissions(assignment_id):
    user_id = session.get('user_id')
    
    # Get assignment
    assignment = Assignment.query.get_or_404(assignment_id)
    
    # Ensure admin owns this assignment
    if assignment.creator_id != user_id:
        flash("You don't have permission to view these submissions", "error")
        return redirect(url_for('admin_dashboard'))
    
    # Get submissions
    submissions = Submission.query.filter_by(
        assignment_id=assignment_id
    ).order_by(Submission.submitted_at.desc()).all()
    
    return render_template(
        "admin/view_submissions.html", 
        assignment=assignment,
        submissions=submissions
    )

@app.route("/admin/submission-details/<int:submission_id>")
@admin_required
def submission_details(submission_id):
    user_id = session.get('user_id')
    
    # Get submission
    submission = Submission.query.get_or_404(submission_id)
    
    # Get assignment
    assignment = Assignment.query.get(submission.assignment_id)
    
    # Ensure admin owns this assignment
    if assignment.creator_id != user_id:
        flash("You don't have permission to view this submission", "error")
        return redirect(url_for('admin_dashboard'))
    
    # Get questions and responses
    questions = Question.query.filter_by(assignment_id=assignment.id).all()
    responses = {}
    
    for question in questions:
        response = QuestionResponse.query.filter_by(
            submission_id=submission_id,
            question_id=question.id
        ).first()
        responses[question.id] = response
    
    return render_template(
        "admin/submission_details.html", 
        submission=submission,
        assignment=assignment,
        questions=questions,
        responses=responses
    )

@app.route("/admin/chat")
@admin_required
def admin_chat():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    # Get organization students
    students = User.query.filter_by(
        organization_id=user.organization_id, 
        role='student'
    ).all()
    
    # Get chat history for the first student if any
    chat_partner = None
    messages = []
    
    if students:
        chat_partner = students[0]
        # Get chat history
        messages = ChatMessage.query.filter(
            ((ChatMessage.sender_id == user_id) & (ChatMessage.receiver_id == chat_partner.id)) |
            ((ChatMessage.sender_id == chat_partner.id) & (ChatMessage.receiver_id == user_id))
        ).order_by(ChatMessage.timestamp).all()
    
    return render_template(
        "admin/chat.html", 
        students=students,
        chat_partner=chat_partner,
        messages=messages
    )

@app.route("/admin/chat/<int:student_id>")
@admin_required
def admin_chat_with_student(student_id):
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    # Get student
    student = User.query.get_or_404(student_id)
    
    # Ensure student is in the same organization
    if student.organization_id != user.organization_id:
        flash("You don't have permission to chat with this student", "error")
        return redirect(url_for('admin_chat'))
    
    # Get organization students
    students = User.query.filter_by(
        organization_id=user.organization_id, 
        role='student'
    ).all()
    
    # Get chat history
    messages = ChatMessage.query.filter(
        ((ChatMessage.sender_id == user_id) & (ChatMessage.receiver_id == student_id)) |
        ((ChatMessage.sender_id == student_id) & (ChatMessage.receiver_id == user_id))
    ).order_by(ChatMessage.timestamp).all()
    
    return render_template(
        "admin/chat.html", 
        students=students,
        chat_partner=student,
        messages=messages
    )

@app.route("/admin/send-message", methods=['POST'])
@admin_required
def admin_send_message():
    user_id = session.get('user_id')
    
    # Get message data
    receiver_id = request.form.get('receiver_id')
    message_text = request.form.get('message')
    
    # Validate data
    if not receiver_id or not message_text:
        return jsonify({'success': False, 'error': 'Missing required fields'})
    
    # Create message
    new_message = ChatMessage(
        sender_id=user_id,
        receiver_id=receiver_id,
        message=message_text,
        timestamp=datetime.now()
    )
    
    db.session.add(new_message)
    db.session.commit()
    
    # Return the new message data
    return jsonify({
        'success': True,
        'message': {
            'id': new_message.id,
            'sender_id': new_message.sender_id,
            'message': new_message.message,
            'timestamp': new_message.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }
    })

@app.route("/admin/get-messages/<int:student_id>")
@admin_required
def admin_get_messages(student_id):
    user_id = session.get('user_id')
    
    # Get last message ID to fetch only newer messages
    last_id = request.args.get('last_id', 0, type=int)
    
    # Get new messages
    messages = ChatMessage.query.filter(
        ((ChatMessage.sender_id == user_id) & (ChatMessage.receiver_id == student_id)) |
        ((ChatMessage.sender_id == student_id) & (ChatMessage.receiver_id == user_id))
    ).filter(
        ChatMessage.id > last_id
    ).order_by(ChatMessage.timestamp).all()
    
    # Format messages for JSON response
    messages_data = [{
        'id': msg.id,
        'sender_id': msg.sender_id,
        'message': msg.message,
        'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    } for msg in messages]
    
    return jsonify({'success': True, 'messages': messages_data})

@app.route("/admin/generate-pdf/<int:submission_id>")
@admin_required
def generate_pdf(submission_id):
    user_id = session.get('user_id')
    
    # Get submission
    submission = Submission.query.get_or_404(submission_id)
    
    # Get assignment
    assignment = Assignment.query.get(submission.assignment_id)
    
    # Ensure admin owns this assignment
    if assignment.creator_id != user_id:
        flash("You don't have permission to generate PDF for this submission", "error")
        return redirect(url_for('admin_dashboard'))
    
    # Get questions and responses
    questions = Question.query.filter_by(assignment_id=assignment.id).all()
    responses = {}
    
    for question in questions:
        response = QuestionResponse.query.filter_by(
            submission_id=submission_id,
            question_id=question.id
        ).first()
        responses[question.id] = response
    
    # Return the template with the special attribute for PDF generation
    return render_template(
        "admin/pdf_template.html", 
        submission=submission,
        assignment=assignment,
        questions=questions,
        responses=responses,
        generate_pdf=True,
        generation_time=datetime.now().strftime('%Y-%m-%d %H:%M')
    )

# Student routes
@app.route("/student/dashboard")
@student_required
def student_dashboard():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    organization = Organization.query.get(user.organization_id)
    
    # Get all assignments for this organization's admins
    admins = User.query.filter_by(
        organization_id=user.organization_id, 
        role='admin'
    ).all()
    
    admin_ids = [admin.id for admin in admins]
    
    assignments = Assignment.query.filter(
        Assignment.creator_id.in_(admin_ids)
    ).order_by(Assignment.created_at.desc()).all()
    
    # Get student submissions
    submissions = Submission.query.filter(
        Submission.user_id == user_id
    ).all()
    
    # Create a dict of assignment_id -> submission
    submission_map = {sub.assignment_id: sub for sub in submissions}
    
    return render_template(
        "student/dashboard.html", 
        user=user,
        organization=organization,
        assignments=assignments,
        submission_map=submission_map,
        current_datetime=datetime.now()
    )

@app.route("/student/assignment/<int:assignment_id>")
@student_required
def view_assignment(assignment_id):
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    # Get assignment
    assignment = Assignment.query.get_or_404(assignment_id)
    
    # Check if admin is in same organization
    admin = User.query.get(assignment.creator_id)
    if admin.organization_id != user.organization_id:
        flash("You don't have permission to view this assignment", "error")
        return redirect(url_for('student_dashboard'))
    
    # Get questions
    questions = Question.query.filter_by(assignment_id=assignment_id).all()
    
    # Check if already submitted
    submission = Submission.query.filter_by(
        assignment_id=assignment_id,
        user_id=user_id
    ).first()
    
    # If submitted, get responses
    responses = {}
    if submission:
        for question in questions:
            response = QuestionResponse.query.filter_by(
                submission_id=submission.id,
                question_id=question.id
            ).first()
            responses[question.id] = response
    
    return render_template(
        "student/assignment_view.html", 
        assignment=assignment,
        questions=questions,
        submission=submission,
        responses=responses
    )

@app.route("/student/upload-answer/<int:question_id>", methods=['POST'])
@student_required
def upload_answer(question_id):
    user_id = session.get('user_id')
    
    # Get question
    question = Question.query.get_or_404(question_id)
    
    # Check if files were uploaded
    if 'images' not in request.files:
        return jsonify({'success': False, 'error': 'No files uploaded'})
    
    files = request.files.getlist('images')
    
    if not files or files[0].filename == '':
        return jsonify({'success': False, 'error': 'No files selected'})
    
    # Create upload directory for this user and question
    user_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], f"user_{user_id}")
    question_upload_dir = os.path.join(user_upload_dir, f"question_{question_id}")
    
    if not os.path.exists(user_upload_dir):
        os.makedirs(user_upload_dir)
    if not os.path.exists(question_upload_dir):
        os.makedirs(question_upload_dir)
    
    # Save files
    image_paths = []
    saved_paths = []  # For OCR processing
    
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Add UUID to ensure unique filename
            unique_filename = f"{uuid.uuid4()}_{filename}"
            # Create paths
            file_path = os.path.join(question_upload_dir, unique_filename)
            # Store path without leading slash
            relative_path = f"user_{user_id}/question_{question_id}/{unique_filename}"
            
            # Save the file
            file.save(file_path)
            image_paths.append(relative_path)
            saved_paths.append(file_path)
    
    if not image_paths:
        return jsonify({'success': False, 'error': 'No valid image files uploaded'})
    
    # Extract text from first image using the absolute path
    extracted_text = extract_text_from_image(saved_paths[0])
    
    # Get first five words
    first_five_words = ' '.join(extracted_text.split()[:5]) if extracted_text else 'Text extraction failed'
    
    # Return the paths, extracted text and preview
    return jsonify({
        'success': True,
        'image_paths': image_paths,
        'extracted_text': extracted_text,
        'first_five_words': first_five_words
    })

@app.route("/student/submit-answer/<int:assignment_id>/<int:question_id>", methods=['POST'])
@student_required
def submit_answer(assignment_id, question_id):
    user_id = session.get('user_id')
    
    # Get question
    question = Question.query.get_or_404(question_id)
    
    # Check if assignment matches
    if question.assignment_id != assignment_id:
        return jsonify({'success': False, 'error': 'Question does not belong to this assignment'})
    
    # Get request data
    data = request.get_json()
    
    image_paths = data.get('image_paths', [])
    extracted_text = data.get('extracted_text', '')
    
    if not extracted_text:
        return jsonify({'success': False, 'error': 'No text extracted from images'})
    
    # Get or create submission
    submission = Submission.query.filter_by(
        assignment_id=assignment_id,
        user_id=user_id
    ).first()
    
    if not submission:
        submission = Submission(
            assignment_id=assignment_id,
            user_id=user_id,
            submitted_at=datetime.now()
        )
        db.session.add(submission)
        db.session.commit()
    
    # Check if there's already a response for this question
    response = QuestionResponse.query.filter_by(
        submission_id=submission.id,
        question_id=question_id
    ).first()
    
    # Evaluate the answer
    word_count_actual = len(extracted_text.split())
    
    # Get size score - compare to expected word count
    size_ratio = min(1.0, word_count_actual / question.word_count) if question.word_count > 0 else 0
    size_score = round(size_ratio * 100, 2)
    
    # Get grammar evaluation
    grammar_eval = evaluate_grammar_with_gemini(extracted_text)
    grammar_score = grammar_eval.get('grammar_score', 70.0)
    grammar_feedback = grammar_eval.get('grammar_feedback', 'Grammar evaluation unavailable.')
    
    # Get relevance score based on evaluation method
    if question.evaluation_method == 'answer_key':
        # Use similarity comparison
        relevance_score = calculate_similarity_nlp(extracted_text, question.answer_key)
        feedback = f"Your answer is {relevance_score}% similar to the expected answer."
    else:
        # Use Gemini API
        evaluation = evaluate_with_gemini(question.question_text, extracted_text)
        relevance_score = evaluation.get('relevance_score', 0.0)
        feedback = evaluation.get('feedback', 'Could not evaluate your answer.')
    
    # Calculate marks based on relevance score
    marks_awarded = (relevance_score / 100) * question.max_marks
    
    # Get first five words
    first_five_words = ' '.join(extracted_text.split()[:5]) if extracted_text else 'Text extraction failed'
    
    # Check for potential plagiarism - if student name is not in the first words
    user = User.query.get(user_id)
    student_name = user.username.lower()
    first_words_lower = first_five_words.lower()
    
    # Check if student name appears in the first five words
    possible_plagiarism = student_name not in first_words_lower
    plagiarism_note = ""
    
    if possible_plagiarism:
        plagiarism_note = f"POSSIBLE PLAGIARISM DETECTED: Student name '{student_name}' not found in the first words: '{first_five_words}'"
        print(f"Plagiarism check for user {user_id}: {plagiarism_note}")
        
        # If plagiarism is suspected, reduce the score
        relevance_score = max(0, relevance_score * 0.7)  # 30% penalty
        marks_awarded = (relevance_score / 100) * question.max_marks
        
        # Update feedback
        feedback = f"[ATTENTION: Possible plagiarism detected] {feedback}"
    
    if response:
        # Update existing response
        response.extracted_text = extracted_text
        response.first_five_words = first_five_words
        response.relevance_score = relevance_score
        response.marks_awarded = marks_awarded
        response.feedback = feedback
        response.image_paths = image_paths
        response.size_score = size_score
        response.grammar_score = grammar_score
        response.word_count_actual = word_count_actual
        response.possible_plagiarism = possible_plagiarism
        response.plagiarism_note = plagiarism_note
    else:
        # Create new response
        response = QuestionResponse(
            submission_id=submission.id,
            question_id=question_id,
            extracted_text=extracted_text,
            first_five_words=first_five_words,
            relevance_score=relevance_score,
            marks_awarded=marks_awarded,
            feedback=feedback,
            image_paths=image_paths,
            size_score=size_score,
            grammar_score=grammar_score,
            word_count_actual=word_count_actual,
            possible_plagiarism=possible_plagiarism,
            plagiarism_note=plagiarism_note
        )
        db.session.add(response)
    
    db.session.commit()
    
    # Update submission with averages
    update_submission_scores(submission.id)
    
    return jsonify({
        'success': True,
        'response': {
            'relevance_score': relevance_score,
            'marks_awarded': marks_awarded,
            'feedback': feedback,
            'size_score': size_score,
            'grammar_score': grammar_score,
            'word_count_actual': word_count_actual
        }
    })

def update_submission_scores(submission_id):
    """Update the submission with average scores from all question responses"""
    # Get all responses for this submission
    responses = QuestionResponse.query.filter_by(submission_id=submission_id).all()
    
    if not responses:
        return
    
    # Calculate averages
    total_marks = sum(response.marks_awarded for response in responses)
    avg_relevance = sum(response.relevance_score for response in responses) / len(responses)
    avg_size_score = sum(response.size_score for response in responses) / len(responses)
    avg_grammar_score = sum(response.grammar_score for response in responses) / len(responses)
    
    # Generate overall feedback
    feedback = f"Overall performance: {avg_relevance:.2f}% relevance. Grammar: {avg_grammar_score:.2f}%. Size compliance: {avg_size_score:.2f}%."
    
    # Update submission
    submission = Submission.query.get(submission_id)
    submission.total_marks = total_marks
    submission.feedback = feedback
    submission.avg_relevance = avg_relevance
    submission.avg_size_score = avg_size_score
    submission.avg_grammar_score = avg_grammar_score
    
    db.session.commit()

@app.route("/student/finalize-submission/<int:assignment_id>", methods=['POST'])
@student_required
def finalize_submission(assignment_id):
    user_id = session.get('user_id')
    
    # Get submission
    submission = Submission.query.filter_by(
        assignment_id=assignment_id,
        user_id=user_id
    ).first()
    
    if not submission:
        return jsonify({'success': False, 'error': 'No submission found'})
    
    # Get assignment and questions
    assignment = Assignment.query.get(assignment_id)
    questions = Question.query.filter_by(assignment_id=assignment_id).all()
    
    # Check if all questions have been answered
    for question in questions:
        response = QuestionResponse.query.filter_by(
            submission_id=submission.id,
            question_id=question.id
        ).first()
        
        if not response:
            return jsonify({
                'success': False, 
                'error': f'Question "{question.question_text}" has not been answered'
            })
    
    # Update submission timestamp
    submission.submitted_at = datetime.now()
    db.session.commit()
    
    return jsonify({'success': True})

@app.route("/student/chat")
@student_required
def student_chat():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    # Get organization admins
    admins = User.query.filter_by(
        organization_id=user.organization_id, 
        role='admin'
    ).all()
    
    # Get chat history for the first admin if any
    chat_partner = None
    messages = []
    
    if admins:
        chat_partner = admins[0]
        # Get chat history
        messages = ChatMessage.query.filter(
            ((ChatMessage.sender_id == user_id) & (ChatMessage.receiver_id == chat_partner.id)) |
            ((ChatMessage.sender_id == chat_partner.id) & (ChatMessage.receiver_id == user_id))
        ).order_by(ChatMessage.timestamp).all()
    
    return render_template(
        "student/chat.html", 
        admins=admins,
        chat_partner=chat_partner,
        messages=messages
    )

@app.route("/student/chat/<int:admin_id>")
@student_required
def student_chat_with_admin(admin_id):
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    # Get admin
    admin = User.query.get_or_404(admin_id)
    
    # Ensure admin is in the same organization
    if admin.organization_id != user.organization_id:
        flash("You don't have permission to chat with this admin", "error")
        return redirect(url_for('student_chat'))
    
    # Get organization admins
    admins = User.query.filter_by(
        organization_id=user.organization_id, 
        role='admin'
    ).all()
    
    # Get chat history
    messages = ChatMessage.query.filter(
        ((ChatMessage.sender_id == user_id) & (ChatMessage.receiver_id == admin_id)) |
        ((ChatMessage.sender_id == admin_id) & (ChatMessage.receiver_id == user_id))
    ).order_by(ChatMessage.timestamp).all()
    
    return render_template(
        "student/chat.html", 
        admins=admins,
        chat_partner=admin,
        messages=messages
    )

@app.route("/student/send-message", methods=['POST'])
@student_required
def student_send_message():
    user_id = session.get('user_id')
    
    # Get message data
    receiver_id = request.form.get('receiver_id')
    message_text = request.form.get('message')
    
    # Validate data
    if not receiver_id or not message_text:
        return jsonify({'success': False, 'error': 'Missing required fields'})
    
    # Create message
    new_message = ChatMessage(
        sender_id=user_id,
        receiver_id=receiver_id,
        message=message_text,
        timestamp=datetime.now()
    )
    
    db.session.add(new_message)
    db.session.commit()
    
    # Return the new message data
    return jsonify({
        'success': True,
        'message': {
            'id': new_message.id,
            'sender_id': new_message.sender_id,
            'message': new_message.message,
            'timestamp': new_message.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }
    })

@app.route("/student/get-messages/<int:admin_id>")
@student_required
def student_get_messages(admin_id):
    user_id = session.get('user_id')
    
    # Get last message ID to fetch only newer messages
    last_id = request.args.get('last_id', 0, type=int)
    
    # Get new messages
    messages = ChatMessage.query.filter(
        ((ChatMessage.sender_id == user_id) & (ChatMessage.receiver_id == admin_id)) |
        ((ChatMessage.sender_id == admin_id) & (ChatMessage.receiver_id == user_id))
    ).filter(
        ChatMessage.id > last_id
    ).order_by(ChatMessage.timestamp).all()
    
    # Format messages for JSON response
    messages_data = [{
        'id': msg.id,
        'sender_id': msg.sender_id,
        'message': msg.message,
        'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    } for msg in messages]
    
    return jsonify({'success': True, 'messages': messages_data})

# Serve uploaded files
@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    """Serve files from the uploads directory"""
    try:
        # Clean the filename to prevent directory traversal
        filename = filename.replace('../', '').replace('..\\', '')
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=False)
    except Exception as e:
        print(f"Error serving file {filename}: {str(e)}")
        abort(404)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
