# models.py
# Database models mapping the schema using Flask-SQLAlchemy

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import secrets
import json

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
    api_token = db.Column(db.String(255), unique=True, nullable=True, default=lambda: secrets.token_hex(32))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships mapping to other user data
    sessions = db.relationship('StudySession', backref='user', lazy=True, cascade="all, delete-orphan")
    plans = db.relationship('StudyPlan', backref='user', lazy=True, cascade="all, delete-orphan")
    quiz_results = db.relationship('QuizResult', backref='user', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        """
        Serialize User profile details, omitting sensitive fields.
        """
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None
        }

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

    def to_dict(self):
        """
        Serialize StudySession details.
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "session_date": self.session_date.strftime("%Y-%m-%d %H:%M:%S") if self.session_date else None,
            "mood": self.mood,
            "study_hours": self.study_hours,
            "sleep_hours": self.sleep_hours,
            "days_left": self.days_left,
            "subjects": [s.strip() for s in self.subjects.split(";") if s.strip()] if self.subjects else [],
            "productivity_score": self.productivity_score,
            "burnout_risk": self.burnout_risk,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None
        }

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

    def to_dict(self):
        """
        Serialize StudyPlan details, deserializing the JSON layout.
        """
        try:
            details = json.loads(self.plan_details)
        except Exception:
            details = self.plan_details

        return {
            "id": self.id,
            "user_id": self.user_id,
            "days_left": self.days_left,
            "subjects": [s.strip() for s in self.subjects.split(";") if s.strip()] if self.subjects else [],
            "study_hours": self.study_hours,
            "sleep_hours": self.sleep_hours,
            "mood": self.mood,
            "productivity_score": self.productivity_score,
            "burnout_risk": self.burnout_risk,
            "plan_details": details,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None
        }

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

    def to_dict(self):
        """
        Serialize QuizResult details, deserializing the answers.
        """
        try:
            results = json.loads(self.results_json)
        except Exception:
            results = self.results_json

        return {
            "id": self.id,
            "user_id": self.user_id,
            "topics": self.topics,
            "score": self.score,
            "total_questions": self.total_questions,
            "results": results,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None
        }

    def __repr__(self):
        return f"<QuizResult {self.id} for User {self.user_id}>"
