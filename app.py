import os
import json
import random
import secrets
import requests as http_requests
import dotenv
from flask import Flask, render_template, request, session, abort
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from study_planner import generate_study_plan, format_study_plan_for_display
from data_handler import save_study_session, get_all_sessions, calculate_weekly_stats

# Load environment variables
dotenv.load_dotenv()

# ================= API SETUP =================
# Direct HTTP calls to OpenAI API (no SDK needed)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

# ---- Startup validation (ASCII-safe for Windows console) ----
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

# ================= SECURITY HARDENING =================

# 1. Rate Limiting setup
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
    # Only validate POST requests
    if request.method == "POST":
        token = request.form.get("csrf_token")
        if not token or token != session.get("csrf_token"):
            return "CSRF Token missing or invalid. Action blocked.", 400

# 3. Secure Response Headers (XSS, Clickjacking, CSP protection)
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

@app.route('/planner')
def planner():
    return render_template('form.html')

@app.route('/generate-plan', methods=['POST'])
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

    save_study_session(
        mood, study_hours, sleep_hours, days_left, subjects,
        raw_plan['productivity_score'],
        raw_plan['burnout_analysis']['risk_level']
    )

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
def quiz():
    topics = request.form.get("topics", "") if request.method == 'POST' else ""
    return render_template("quiz_form.html", topics=topics)


@app.route('/generate-quiz', methods=['POST'])
@limiter.limit("5 per minute")
def generate_quiz():
    topics = request.form.get("topics")

    questions = generate_quiz_with_openai(topics)

    if not questions:
        questions = get_fallback_quiz(topics)

    session["quiz"] = questions

    return render_template("quiz.html", questions=questions)


@app.route('/submit-quiz', methods=['POST'])
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

    return render_template(
        "quiz_result.html",
        score=score,
        total=len(questions),
        results=results
    )


@app.route('/history')
def history():
    sessions = get_all_sessions()
    stats = calculate_weekly_stats(sessions)
    return render_template('history.html', sessions=sessions, stats=stats)


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)