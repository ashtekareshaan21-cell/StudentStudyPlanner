import os
import json
import random
import secrets
import bcrypt
import requests as http_requests
import dotenv
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, session, abort, redirect, g, jsonify

from study_planner import generate_study_plan, format_study_plan_for_display
from data_handler import save_study_session, get_all_sessions, calculate_weekly_stats

# Load environment variables
dotenv.load_dotenv()

# ================= API SETUP =================
# Direct HTTP calls to OpenAI API (no SDK needed)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

# ---- Startup validation ----
if not OPENAI_API_KEY:
    print("[ERROR] OPENAI_API_KEY is not set. Quiz will use fallback questions.")
elif not OPENAI_API_KEY.startswith("sk-"):
    print("[ERROR] OPENAI_API_KEY looks invalid (does not start with sk-).")
else:
    print("[OK] OpenAI API key loaded (prefix: %s...)" % OPENAI_API_KEY[:12])

app = Flask(__name__)

# Secure secret key loading
app.secret_key = os.getenv("FLASK_SECRET_KEY")
if not app.secret_key:
    print("[WARN] FLASK_SECRET_KEY is not set. Using a temporary random key for safety.")
    app.secret_key = secrets.token_hex(32)

# ================= DATABASE & MODELS CONFIGURATION =================
# Dynamic DB URI: PostgreSQL in production, SQLite fallback locally
db_url = os.getenv("DATABASE_URL")
if db_url:
    # SQLAlchemy 1.4+ requires postgresql:// scheme
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    # Inject pg8000 dialect for pure-Python driver compatibility on Python 3.15
    if "postgresql" in db_url and "+pg8000" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///smart_study.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize the Flask-SQLAlchemy integration
from models import db, User, StudySession, StudyPlan, QuizResult
db.init_app(app)

# Initialize Flask-Migrate for database schema migrations
from flask_migrate import Migrate
migrate = Migrate(app, db)

# Ensure the database tables are created on boot as fallback
with app.app_context():
    db.create_all()


# ================= SECURITY HARDENING =================

# 1. Rate Limiting setup
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# 2. CSRF Protection
@app.before_request
def generate_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)

@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=session.get("csrf_token", ""))

@app.before_request
def validate_csrf():
    # Exclude API endpoints from CSRF verification
    if request.path.startswith("/api/"):
        return
        
    if request.method == "POST":
        token = request.form.get("csrf_token")
        if not token or token != session.get("csrf_token"):
            return "CSRF Token missing or invalid. Action blocked.", 400

# 3. Secure Response Headers
@app.after_request
def add_security_headers(response):
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "font-src 'self'; "
        "img-src 'self' data:; "
        "connect-src 'self' https://api.openai.com; "
        "frame-ancestors 'none'; "
        "object-src 'none';"
    )
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

# ================= AUTHENTICATION DECORATORS =================
def login_required(f):
    """
    Decorator that checks if a user is in the active session.
    If not, redirects them to the login screen with an error state.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return render_template("login.html", error="Please log in to access this page.")
        return f(*args, **kwargs)
    return decorated_function

def api_login_required(f):
    """
    Hybrid decorator that validates browser session OR stateless API Bearer token.
    On success, stores the resolved User instance in Flask's g.current_user context.
    On failure, returns a JSON error response instead of a template redirect.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = None
        
        # 1. Check for stateless Authorization Bearer token header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            if token:
                user = User.query.filter_by(api_token=token).first()
                
        # 2. Check for active session cookie fallback
        if not user and "user_id" in session:
            user = User.query.get(session["user_id"])
            
        # 3. Handle unauthorized request
        if not user:
            return jsonify({"error": "Unauthorized. Please log in or provide a valid API token."}), 401
            
        # Bind user to request context global 'g'
        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function

# ================= MOTIVATION =================
def get_motivation():
    quotes = [
        "You've got this!",
        "Stay consistent, success will follow!",
        "Small steps every day lead to big results!",
        "Focus now, shine later!",
        "Discipline beats motivation!",
        "Progress > Perfection!"
    ]
    return random.choice(quotes)

@app.context_processor
def inject_motivation():
    return dict(motivation_quote=get_motivation())

# ================= QUIZ FUNCTION =================
def generate_quiz_with_openai(topics):
    if not OPENAI_API_KEY or not OPENAI_API_KEY.startswith("sk-"):
        print("[WARN] No valid API key - skipping OpenAI call.")
        return None

    prompt = f"""
You are an expert university professor and technical interviewer.

Generate EXACTLY 6 technically accurate MCQs on the topic: {topics}

The questions MUST test REAL understanding of the topic itself.

IMPORTANT:
Do NOT generate generic learning-skill questions.
Do NOT ask vague questions like:
- "How would you apply knowledge?"
- "Which approach is best for learning?"
- "Why is understanding important?"

Instead:
Generate DIRECT topic-based technical questions.

========================
QUESTION REQUIREMENTS
========================

1. Questions must:
- Be specifically about {topics}
- Test conceptual understanding
- Include real technical logic
- Be suitable for engineering/university exams
- Feel like actual academic MCQs

2. Include:
- Definitions
- Internal working
- Use cases
- Comparisons
- Code/output reasoning (if topic is programming)
- Real-world applications

3. Difficulty Levels:
- Q1–Q2 → Remember
- Q3–Q4 → Understand
- Q5–Q6 → Apply

4. VERY IMPORTANT:
For programming/computer science topics:
- Include code snippets if useful
- Ask output-based or logic-based questions
- Use realistic terminology

========================
EXAMPLE OF GOOD QUESTION
========================

Topic: Encapsulation

GOOD:
"Which feature of encapsulation helps prevent direct modification of object data?"

BAD:
"How would you apply knowledge of encapsulation?"

========================
OPTIONS RULES
========================

- Every option must be meaningful
- Avoid obvious wrong answers
- Avoid repetitive structures
- Avoid placeholders

========================
OUTPUT FORMAT
========================

Return ONLY valid JSON.

{{
  "questions": [
    {{
      "id": 1,
      "question": "Actual technical question",
      "level": "Remember",
      "options": {{
        "A": "Meaningful option",
        "B": "Meaningful option",
        "C": "Meaningful option",
        "D": "Meaningful option"
      }},
      "correct_answer": "A",
      "explanation": "Technical explanation"
    }}
  ]
}}

========================
FINAL RULES
========================

- EXACTLY 6 questions
- NO generic educational questions
- Questions must directly test the topic itself
- Make questions realistic and exam-oriented
"""

    try:
        print("[INFO] Calling OpenAI API...")

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "You must return ONLY valid JSON. No explanation."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
        }

        resp = http_requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=30)

        # ---- Debug: print API response errors clearly ----
        if resp.status_code != 200:
            error_body = resp.text[:400]
            print("=" * 60)
            print("[ERROR] OpenAI API returned HTTP %d" % resp.status_code)
            if resp.status_code == 401:
                print("  Reason: Invalid or expired API key")
                print("  Fix: Get a new key at https://platform.openai.com/api-keys")
            elif resp.status_code == 429:
                print("  Reason: Rate limit or quota exceeded")
                print("  Fix: Check usage at https://platform.openai.com/usage")
            elif resp.status_code >= 500:
                print("  Reason: OpenAI server error (temporary)")
            else:
                print("  Response: %s" % error_body)
            print("=" * 60)
            return None

        result = resp.json()
        text = result["choices"][0]["message"]["content"]
        print("[INFO] Raw response length: %d chars" % len(text))

        # Clean response (strip markdown fences)
        text = text.replace("```json", "").replace("```", "").strip()

        data = json.loads(text)
        questions = data.get("questions", [])

        if len(questions) != 6:
            print("[WARN] Expected 6 questions, got %d" % len(questions))
            return None

        print("[OK] Successfully parsed 6 questions from OpenAI")
        return questions

    except http_requests.exceptions.Timeout:
        print("[ERROR] OpenAI request timed out (30s)")
        return None
    except http_requests.exceptions.ConnectionError:
        print("[ERROR] Could not connect to OpenAI. Check internet.")
        return None
    except json.JSONDecodeError as e:
        print("[ERROR] JSON parse error: %s" % e)
        return None
    except Exception as e:
        print("[ERROR] API error: %s - %s" % (type(e).__name__, e))
        return None


# ================= FALLBACK =================
def get_fallback_quiz(topics):
    print("[WARN] Using fallback quiz for: %s" % topics)
    base = topics if topics else "the subject"
    return [
        {
            "id": 1,
            "question": "What is the primary definition or concept of %s?" % base,
            "level": "Remember",
            "options": {"A": "A foundational principle", "B": "An unrelated fact", "C": "A historical event", "D": "A mathematical formula"},
            "correct_answer": "A",
            "explanation": "The primary concept of %s is a foundational principle central to understanding the subject." % base
        },
        {
            "id": 2,
            "question": "Which of the following best describes a key characteristic of %s?" % base,
            "level": "Remember",
            "options": {"A": "It is abstract and theoretical", "B": "It has practical real-world applications", "C": "It is purely mathematical", "D": "It is only relevant historically"},
            "correct_answer": "B",
            "explanation": "%s has important practical applications that make it relevant in real-world scenarios." % base
        },
        {
            "id": 3,
            "question": "How does %s relate to other concepts in its field?" % base,
            "level": "Understand",
            "options": {"A": "It is completely isolated", "B": "It forms the basis for many related ideas", "C": "It contradicts most other concepts", "D": "It is only applicable in one narrow scenario"},
            "correct_answer": "B",
            "explanation": "Understanding %s provides a foundation for grasping many related concepts in the same domain." % base
        },
        {
            "id": 4,
            "question": "Why is studying %s important for learners in this field?" % base,
            "level": "Understand",
            "options": {"A": "It is rarely tested", "B": "It helps build critical thinking skills", "C": "It has no modern relevance", "D": "It only matters for advanced practitioners"},
            "correct_answer": "B",
            "explanation": "Studying %s builds critical thinking and provides a framework for solving complex problems." % base
        },
        {
            "id": 5,
            "question": "In a practical scenario, how would you apply knowledge of %s?" % base,
            "level": "Apply",
            "options": {"A": "By memorizing definitions only", "B": "By identifying patterns and solving related problems", "C": "By ignoring underlying principles", "D": "By relying solely on intuition"},
            "correct_answer": "B",
            "explanation": "Applying %s effectively means recognizing patterns and using core principles to solve real problems." % base
        },
        {
            "id": 6,
            "question": "Which approach would be most effective when learning %s deeply?" % base,
            "level": "Apply",
            "options": {"A": "Passive reading only", "B": "Practice problems and active recall", "C": "Skipping foundational concepts", "D": "Memorizing without understanding"},
            "correct_answer": "B",
            "explanation": "Active recall and practice problems are proven strategies for deeply learning topics like %s." % base
        },
    ]


# ================= ROUTES =================

@app.route('/')
def home():
    return render_template("home.html")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if "user_id" in session:
        return redirect('/')
        
    if request.method == 'POST':
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        
        # Validation checks
        if not username or not email or not password:
            return render_template("register.html", error="All fields are required.")
            
        if len(password) < 6:
            return render_template("register.html", error="Password must be at least 6 characters.")
            
        if password != confirm_password:
            return render_template("register.html", error="Passwords do not match.")
            
        # Check if user already exists
        existing_username = User.query.filter_by(username=username).first()
        if existing_username:
            return render_template("register.html", error="Username is already taken.")
            
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            return render_template("register.html", error="Email is already registered.")
            
        # Hash password using bcrypt salt
        salt = bcrypt.gensalt()
        pw_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
        
        # Create and write user
        new_user = User(username=username, email=email, password_hash=pw_hash)
        try:
            db.session.add(new_user)
            db.session.commit()
            return render_template("login.html", success="Registration successful. Please log in.")
        except Exception as e:
            db.session.rollback()
            print(f"[AUTH ERROR] Failed user creation: {e}")
            return render_template("register.html", error="A database error occurred. Try again.")
            
    return render_template("register.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if "user_id" in session:
        return redirect('/')
        
    if request.method == 'POST':
        username_or_email = request.form.get("username_or_email", "").strip()
        password = request.form.get("password", "")
        
        if not username_or_email or not password:
            return render_template("login.html", error="Please fill in all fields.")
            
        # Query user
        user = User.query.filter((User.username == username_or_email) | (User.email == username_or_email)).first()
        
        # Check password hash validity
        if user and bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
            session["user_id"] = user.id
            session["username"] = user.username
            return redirect('/')
        else:
            return render_template("login.html", error="Invalid username/email or password.")
            
    return render_template("login.html")

@app.route('/logout')
def logout():
    session.pop("user_id", None)
    session.pop("username", None)
    return redirect('/')


@app.route('/planner')
@login_required
def planner():
    return render_template('form.html')

@app.route('/generate-plan', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def generate_plan():
    mood = int(request.form.get('mood', 3))
    study_hours = float(request.form.get('study_hours', 2))
    days_left = int(request.form.get('days_left', 7))
    subjects_raw = request.form.get('subjects', 'General')
    sleep_hours = float(request.form.get('sleep_hours', 7))

    subjects = [s.strip() for s in subjects_raw.split(',') if s.strip()]
    if not subjects:
        subjects = ['General']

    raw_plan = generate_study_plan(mood, study_hours, days_left, subjects, sleep_hours)
    plan = format_study_plan_for_display(raw_plan)

    # Save session with associated user ID
    save_study_session(
        session["user_id"], mood, study_hours, sleep_hours, days_left, subjects,
        raw_plan['productivity_score'],
        raw_plan['burnout_analysis']['risk_level']
    )

    # Save study plan details in the database
    try:
        new_plan = StudyPlan(
            user_id=session["user_id"],
            days_left=days_left,
            subjects=";".join(subjects),
            study_hours=study_hours,
            sleep_hours=sleep_hours,
            mood=mood,
            productivity_score=raw_plan['productivity_score'],
            burnout_risk=raw_plan['burnout_analysis']['risk_level'],
            plan_details=json.dumps(plan)
        )
        db.session.add(new_plan)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] Failed to save study plan to database: {e}")

    return render_template(
        'result.html',
        plan=plan,
        subjects=subjects,
        study_hours=study_hours,
        mood=mood,
        sleep_hours=sleep_hours,
        days_left=days_left
    )


@app.route('/quiz', methods=['GET', 'POST'])
@login_required
def quiz():
    topics = request.form.get("topics", "") if request.method == 'POST' else ""
    return render_template("quiz_form.html", topics=topics)


@app.route('/generate-quiz', methods=['POST'])
@login_required
@limiter.limit("5 per minute")
def generate_quiz():
    topics = request.form.get("topics")

    questions = generate_quiz_with_openai(topics)

    if not questions:
        questions = get_fallback_quiz(topics)

    session["quiz"] = questions
    session["quiz_topics"] = topics or "General Study"

    return render_template("quiz.html", questions=questions)


@app.route('/submit-quiz', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def submit_quiz():
    questions = session.get("quiz", [])
    score = 0
    results = []

    for q in questions:
        user_ans = request.form.get("q%s" % q['id'])
        correct = q["correct_answer"]

        is_correct = user_ans == correct
        if is_correct:
            score += 1

        results.append({
            "question": q["question"],
            "user": user_ans,
            "correct": correct,
            "explanation": q["explanation"],
            "is_correct": is_correct
        })

    # Save quiz result in database
    try:
        topics = session.get("quiz_topics", "General Study")
        quiz_result = QuizResult(
            user_id=session["user_id"],
            topics=topics,
            score=score,
            total_questions=len(questions),
            results_json=json.dumps(results)
        )
        db.session.add(quiz_result)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] Failed to save quiz result to database: {e}")

    return render_template(
        "quiz_result.html",
        score=score,
        total=len(questions),
        results=results
    )


@app.route('/history')
@login_required
def history():
    sessions = get_all_sessions(session["user_id"])
    stats = calculate_weekly_stats(sessions)
    return render_template('history.html', sessions=sessions, stats=stats, session_count=len(sessions))


# ================= REST API ENDPOINTS =================

@app.route('/api/v1/token', methods=['GET'])
@login_required
def get_api_token():
    """
    Retrieve the authenticated user's API token.
    Used by clients to bootstrap token-based Authorization.
    """
    user = User.query.get(session["user_id"])
    return jsonify({"api_token": user.api_token})

@app.route('/api/v1/sessions', methods=['GET'])
@api_login_required
def api_get_sessions():
    """
    Get all study sessions for the authenticated user.
    """
    sessions = StudySession.query.filter_by(user_id=g.current_user.id).order_by(StudySession.id.asc()).all()
    return jsonify([s.to_dict() for s in sessions])

@app.route('/api/v1/sessions', methods=['POST'])
@api_login_required
def api_create_session():
    """
    Create a new study session for the user.
    Accepts JSON body and performs input validation.
    """
    data = request.get_json() or {}
    
    # Validation checks
    try:
        mood = int(data.get("mood", 3))
        study_hours = float(data.get("study_hours", 2.0))
        sleep_hours = float(data.get("sleep_hours", 7.0))
        days_left = int(data.get("days_left", 7))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid numeric types for mood, study_hours, sleep_hours, or days_left."}), 400
        
    if not (1 <= mood <= 5):
        return jsonify({"error": "Mood must be an integer between 1 and 5."}), 400
    if study_hours < 0 or sleep_hours < 0 or days_left < 0:
        return jsonify({"error": "Study hours, sleep hours, and days left must be non-negative."}), 400
        
    subjects_raw = data.get("subjects", ["General"])
    if not isinstance(subjects_raw, list):
        subjects_raw = [str(subjects_raw)]
    subjects_raw = [s.strip() for s in subjects_raw if s.strip()]
    if not subjects_raw:
        subjects_raw = ["General"]
    subjects_str = ";".join(subjects_raw)
    
    # Dynamic calculations if missing
    from analyzer import calculate_productivity_score, detect_burnout
    
    productivity_score = data.get("productivity_score")
    if productivity_score is None:
        productivity_score = calculate_productivity_score(mood, sleep_hours, study_hours)
    else:
        try:
            productivity_score = float(productivity_score)
        except (ValueError, TypeError):
            return jsonify({"error": "Productivity score must be a number."}), 400
            
    burnout_risk = data.get("burnout_risk")
    if burnout_risk is None:
        burnout_risk = detect_burnout(study_hours, sleep_hours)['risk_level']
    else:
        burnout_risk = str(burnout_risk)
        
    try:
        new_session = StudySession(
            user_id=g.current_user.id,
            session_date=datetime.utcnow(),
            mood=mood,
            study_hours=study_hours,
            sleep_hours=sleep_hours,
            days_left=days_left,
            subjects=subjects_str,
            productivity_score=productivity_score,
            burnout_risk=burnout_risk
        )
        db.session.add(new_session)
        db.session.commit()
        return jsonify(new_session.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to save session: {str(e)}"}), 500

@app.route('/api/v1/plans', methods=['GET'])
@api_login_required
def api_get_plans():
    """
    Get all generated AI study plans for the user.
    """
    plans = StudyPlan.query.filter_by(user_id=g.current_user.id).order_by(StudyPlan.id.asc()).all()
    return jsonify([p.to_dict() for p in plans])

@app.route('/api/v1/quiz-results', methods=['GET'])
@api_login_required
def api_get_quiz_results():
    """
    Get all quiz results for the user.
    """
    results = QuizResult.query.filter_by(user_id=g.current_user.id).order_by(QuizResult.id.asc()).all()
    return jsonify([r.to_dict() for r in results])


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)