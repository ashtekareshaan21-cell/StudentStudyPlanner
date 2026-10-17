import os
import json
import random
import secrets
import bcrypt
import requests as http_requests
import dotenv
import html
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
from models import db, User, StudySession, StudyPlan, QuizResult, Task
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
        token = (
            request.form.get("csrf_token") or 
            request.headers.get("X-CSRFToken") or 
            (request.get_json(silent=True) or {}).get("csrf_token")
        )
        if not token or token != session.get("csrf_token"):
            return "CSRF Token missing or invalid. Action blocked.", 400

# 3. Secure Response Headers
@app.after_request
def add_security_headers(response):
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
        "font-src 'self'; "
        "img-src 'self' data: https://unpkg.com https://fastly.jsdelivr.net https://cdn.redoc.ly; "
        "connect-src 'self' https://api.openai.com; "
        "worker-src 'self' blob:; "
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
@limiter.limit("3 per minute")
def register():
    if "user_id" in session:
        return redirect('/')
        
    if request.method == 'POST':
        username = html.escape(request.form.get("username", "").strip())
        email = html.escape(request.form.get("email", "").strip())
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
@limiter.limit("5 per minute")
def login():
    if "user_id" in session:
        return redirect('/')
        
    if request.method == 'POST':
        username_or_email = html.escape(request.form.get("username_or_email", "").strip())
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
    plans_query = StudyPlan.query.filter_by(user_id=session["user_id"]).order_by(StudyPlan.id.desc()).limit(15).all()
    
    recent_plans = []
    mood_emoji_map = {1: "😢", 2: "🙁", 3: "😐", 4: "🙂", 5: "😄"}
    
    from study_planner import generate_schedule_blocks, calculate_risk_index
    
    for p in plans_query:
        details = {}
        if p.plan_details:
            try:
                details = json.loads(p.plan_details)
            except Exception:
                details = {}
                
        risk_index = details.get("risk_index")
        if risk_index is None:
            risk_index = calculate_risk_index(p.study_hours, p.sleep_hours, p.mood)
            
        subj_list = [s.strip() for s in p.subjects.split(";") if s.strip()]
        recent_plans.append({
            "id": p.id,
            "date_formatted": p.created_at.strftime("%d %b, %H:%M") if p.created_at else "Recent",
            "mood": p.mood,
            "mood_emoji": mood_emoji_map.get(p.mood, "😐"),
            "sleep_hours": f"{p.sleep_hours:g}",
            "study_hours": p.study_hours,
            "subjects_display": ", ".join(subj_list) if subj_list else "General",
            "risk_index": risk_index,
            "plan_details": details
        })
    
    # Active blocks for right-side timeline
    active_blocks = []
    active_plan_id = None
    if recent_plans and recent_plans[0].get("plan_details", {}).get("blocks"):
        active_blocks = recent_plans[0]["plan_details"]["blocks"]
        active_plan_id = recent_plans[0]["id"]
    else:
        default_schedule = generate_schedule_blocks(start_time="18:00", subjects=["Codex"], study_hours=5.0, mood=4, sleep_hours=7.0)
        active_blocks = default_schedule["blocks"]

    return render_template(
        'form.html',
        recent_plans=recent_plans,
        active_blocks=active_blocks,
        active_plan_id=active_plan_id
    )

@app.route('/generate-plan', methods=['POST'])
@login_required
@limiter.limit("30 per minute")
def generate_plan():
    is_json = request.is_json or request.headers.get("Content-Type") == "application/json"
    data = request.get_json(silent=True) or {} if is_json else request.form

    # 1. Parse parameters
    try:
        mood = int(data.get('mood', 3))
    except (ValueError, TypeError):
        mood = 3

    try:
        study_hours = float(data.get('study_hours', 5.0))
    except (ValueError, TypeError):
        study_hours = 5.0

    try:
        sleep_hours = float(data.get('sleep_hours', 7.0))
    except (ValueError, TypeError):
        sleep_hours = 7.0

    start_time = data.get('start_time', '18:00')

    # 2. Parse subjects
    subject_dicts = []
    subject_names = []
    days_left_val = 7

    if is_json and "subjects" in data and isinstance(data["subjects"], list):
        for s in data["subjects"]:
            if isinstance(s, dict):
                s_name = html.escape(str(s.get("name", "")).strip())
                if s_name:
                    d_left = int(s.get("days_left", 7))
                    c_level = int(s.get("complexity", 3))
                    topics = html.escape(str(s.get("topics", "")).strip())
                    subject_dicts.append({
                        "name": s_name,
                        "days_left": d_left,
                        "complexity": c_level,
                        "topics": topics
                    })
                    subject_names.append(s_name)
                    days_left_val = d_left
            elif isinstance(s, str) and s.strip():
                name = html.escape(s.strip())
                subject_dicts.append({"name": name, "days_left": 7, "complexity": 3, "topics": ""})
                subject_names.append(name)
    else:
        names = request.form.getlist('subject_name[]') or request.form.getlist('subjects[]')
        days = request.form.getlist('days_left[]')
        complexities = request.form.getlist('complexity[]')
        topics_list = request.form.getlist('topics[]')

        if names:
            for i, n in enumerate(names):
                cleaned_name = html.escape(n.strip())
                if cleaned_name:
                    d = int(days[i]) if i < len(days) and days[i].isdigit() else 7
                    c = int(complexities[i]) if i < len(complexities) and complexities[i].isdigit() else 3
                    top = html.escape(topics_list[i].strip()) if i < len(topics_list) else ""
                    subject_dicts.append({
                        "name": cleaned_name,
                        "days_left": d,
                        "complexity": c,
                        "topics": top
                    })
                    subject_names.append(cleaned_name)
                    days_left_val = d

        if not subject_names:
            subjects_raw = data.get('subjects', 'Codex')
            subject_names = [html.escape(s.strip()) for s in str(subjects_raw).split(',') if s.strip()]
            for sn in subject_names:
                subject_dicts.append({"name": sn, "days_left": int(data.get('days_left', 7)), "complexity": 3, "topics": ""})

    if not subject_names:
        subject_names = ['Codex']
        subject_dicts = [{"name": "Codex", "days_left": 7, "complexity": 3, "topics": ""}]

    # 3. Generate adaptive plan
    from study_planner import generate_schedule_blocks, calculate_risk_index
    raw_plan = generate_study_plan(mood, study_hours, days_left_val, subject_names, sleep_hours)
    
    # Generate the schedule timeline with subject rotation and topics
    schedule_info = generate_schedule_blocks(
        start_time=start_time,
        subjects=subject_dicts,
        study_hours=study_hours,
        mood=mood,
        sleep_hours=sleep_hours
    )
    raw_plan["schedule"] = schedule_info
    raw_plan["risk_index"] = schedule_info["risk_index"]
    raw_plan["blocks"] = schedule_info["blocks"]

    plan = format_study_plan_for_display(raw_plan)
    plan["blocks"] = schedule_info["blocks"]
    plan["risk_index"] = schedule_info["risk_index"]
    plan["subjects_data"] = subject_dicts

    # Save session
    save_study_session(
        session["user_id"], mood, study_hours, sleep_hours, days_left_val, subject_names,
        raw_plan['productivity_score'],
        raw_plan['burnout_analysis']['risk_level']
    )

    # Save study plan details in the database
    new_plan = None
    try:
        new_plan = StudyPlan(
            user_id=session["user_id"],
            days_left=days_left_val,
            subjects=";".join(subject_names),
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

    # Return JSON response for AJAX requests
    if is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        mood_emoji_map = {1: "😢", 2: "🙁", 3: "😐", 4: "🙂", 5: "😄"}
        return jsonify({
            "success": True,
            "plan_id": new_plan.id if new_plan else None,
            "date_formatted": new_plan.created_at.strftime("%d %b, %H:%M") if (new_plan and new_plan.created_at) else "Just now",
            "mood": mood,
            "mood_emoji": mood_emoji_map.get(mood, "😐"),
            "sleep_hours": f"{sleep_hours:g}",
            "study_hours": study_hours,
            "subjects_display": ", ".join(subject_names),
            "risk_index": schedule_info["risk_index"],
            "blocks": schedule_info["blocks"]
        })

    return render_template(
        'result.html',
        plan=plan,
        mood=mood,
        study_hours=study_hours,
        days_left=days_left_val,
        sleep_hours=sleep_hours,
        subjects=subject_names,
        raw_plan=raw_plan
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

@app.route('/api/v1/plans/<int:plan_id>', methods=['GET'])
@api_login_required
def api_get_single_plan(plan_id):
    """
    Get a specific study plan by ID for the authenticated user.
    """
    plan = StudyPlan.query.filter_by(id=plan_id, user_id=g.current_user.id).first()
    if not plan:
        return jsonify({"error": "Plan not found."}), 404
    return jsonify(plan.to_dict())

@app.route('/api/v1/plans/<int:plan_id>', methods=['DELETE'])
@api_login_required
def api_delete_plan(plan_id):
    """
    Delete a study plan by ID for the authenticated user.
    """
    plan = StudyPlan.query.filter_by(id=plan_id, user_id=g.current_user.id).first()
    if not plan:
        return jsonify({"error": "Plan not found."}), 404
    try:
        db.session.delete(plan)
        db.session.commit()
        return jsonify({"message": "Plan deleted successfully."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to delete plan: {str(e)}"}), 500

@app.route('/api/v1/quiz-results', methods=['GET'])
@api_login_required
def api_get_quiz_results():
    """
    Get all quiz results for the user.
    """
    results = QuizResult.query.filter_by(user_id=g.current_user.id).order_by(QuizResult.id.asc()).all()
    return jsonify([r.to_dict() for r in results])


# ================= TASK MANAGEMENT UI & API ROUTES =================

@app.route('/tasks')
@login_required
def tasks_page():
    """
    Renders the task board page interface.
    """
    return render_template('tasks.html')

@app.route('/api/v1/tasks', methods=['GET'])
@api_login_required
def api_get_tasks():
    """
    Retrieve all tasks for the authenticated user.
    """
    tasks = Task.query.filter_by(user_id=g.current_user.id).order_by(Task.id.asc()).all()
    return jsonify([t.to_dict() for t in tasks])

@app.route('/api/v1/tasks', methods=['POST'])
@api_login_required
def api_create_task():
    """
    Create a new task for the authenticated user.
    """
    data = request.get_json() or {}
    title = html.escape(data.get("title", "").strip())
    if not title:
        return jsonify({"error": "Task title is required."}), 400

    desc_raw = data.get("description")
    description = html.escape(desc_raw.strip()) if desc_raw and desc_raw.strip() else None
    priority = data.get("priority", "Medium").strip()
    if priority not in ["Low", "Medium", "High"]:
        return jsonify({"error": "Priority must be one of: Low, Medium, High."}), 400

    due_date_str = data.get("due_date", "").strip()
    due_date = None
    if due_date_str:
        try:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "Invalid due_date format. Use YYYY-MM-DD."}), 400

    try:
        new_task = Task(
            user_id=g.current_user.id,
            title=title,
            description=description,
            due_date=due_date,
            priority=priority,
            status="Pending"
        )
        db.session.add(new_task)
        db.session.commit()
        return jsonify(new_task.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to create task: {str(e)}"}), 500

@app.route('/api/v1/tasks/<int:task_id>', methods=['PUT'])
@api_login_required
def api_update_task(task_id):
    """
    Update details (e.g. status, title, priority) of an existing task.
    """
    task = Task.query.filter_by(id=task_id, user_id=g.current_user.id).first()
    if not task:
        return jsonify({"error": "Task not found."}), 404

    data = request.get_json() or {}

    # Update fields if provided
    if "title" in data:
        title = html.escape(data["title"].strip())
        if not title:
            return jsonify({"error": "Task title cannot be empty."}), 400
        task.title = title

    if "description" in data:
        desc_raw = data["description"]
        task.description = html.escape(desc_raw.strip()) if desc_raw and desc_raw.strip() else None

    if "priority" in data:
        priority = data["priority"].strip()
        if priority not in ["Low", "Medium", "High"]:
            return jsonify({"error": "Priority must be one of: Low, Medium, High."}), 400
        task.priority = priority

    if "status" in data:
        status = data["status"].strip()
        if status not in ["Pending", "In Progress", "Completed"]:
            return jsonify({"error": "Status must be one of: Pending, In Progress, Completed."}), 400
        task.status = status

    if "due_date" in data:
        due_date_str = data["due_date"]
        if due_date_str:
            due_date_str = due_date_str.strip()
            try:
                task.due_date = datetime.strptime(due_date_str, "%Y-%m-%d")
            except ValueError:
                return jsonify({"error": "Invalid due_date format. Use YYYY-MM-DD."}), 400
        else:
            task.due_date = None

    try:
        db.session.commit()
        return jsonify(task.to_dict())
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to update task: {str(e)}"}), 500

@app.route('/api/v1/tasks/<int:task_id>', methods=['DELETE'])
@api_login_required
def api_delete_task(task_id):
    """
    Delete a task.
    """
    task = Task.query.filter_by(id=task_id, user_id=g.current_user.id).first()
    if not task:
        return jsonify({"error": "Task not found."}), 404

    try:
        db.session.delete(task)
        db.session.commit()
        return jsonify({"message": "Task deleted successfully."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to delete task: {str(e)}"}), 500


@app.route('/docs')
def docs_index():
    """
    Redirect /docs to the Swagger UI page as default.
    """
    return redirect('/docs/swagger')

@app.route('/docs/swagger')
def docs_swagger():
    """
    Renders Swagger UI documentation panel.
    """
    return render_template('swagger_docs.html')

@app.route('/docs/redoc')
def docs_redoc():
    """
    Renders ReDoc documentation panel.
    """
    return render_template('redoc_docs.html')


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)