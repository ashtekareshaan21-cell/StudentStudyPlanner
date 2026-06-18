# models.py
# Database models mapping the schema using Flask-SQLAlchemy

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Initialize the SQLAlchemy object
db = SQLAlchemy()

class User(db.Model):
    """
    User database model storing authentication and registration profiles.
    """
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships mapping to other user data
    sessions = db.relationship('StudySession', backref='user', lazy=True, cascade="all, delete-orphan")
    plans = db.relationship('StudyPlan', backref='user', lazy=True, cascade="all, delete-orphan")
    quiz_results = db.relationship('QuizResult', backref='user', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.username}>"


class StudySession(db.Model):
    """
    Model representing completed/logged study sessions.
    """
    __tablename__ = 'study_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    session_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    mood = db.Column(db.Integer, nullable=False)
    study_hours = db.Column(db.Float, nullable=False)
    sleep_hours = db.Column(db.Float, nullable=False)
    days_left = db.Column(db.Integer, nullable=False)
    subjects = db.Column(db.Text, nullable=False)  # stored as semicolon-separated string
    productivity_score = db.Column(db.Float, nullable=False)
    burnout_risk = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<StudySession {self.id} for User {self.user_id}>"


class StudyPlan(db.Model):
    """
    Model representing generated AI study plan templates.
    """
    __tablename__ = 'study_plans'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    days_left = db.Column(db.Integer, nullable=False)
    subjects = db.Column(db.Text, nullable=False)
    study_hours = db.Column(db.Float, nullable=False)
    sleep_hours = db.Column(db.Float, nullable=False)
    mood = db.Column(db.Integer, nullable=False)
    productivity_score = db.Column(db.Float, nullable=False)
    burnout_risk = db.Column(db.String(50), nullable=False)
    plan_details = db.Column(db.Text, nullable=False)  # JSON-serialized layout details
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<StudyPlan {self.id} for User {self.user_id}>"


class QuizResult(db.Model):
    """
    Model representing scores and answers from OpenAI or fallback quizzes.
    """
    __tablename__ = 'quiz_results'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    topics = db.Column(db.Text, nullable=False)
    score = db.Column(db.Integer, nullable=False)
    total_questions = db.Column(db.Integer, nullable=False)
    results_json = db.Column(db.Text, nullable=False)  # JSON-serialized responses
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<QuizResult {self.id} for User {self.user_id}>"

