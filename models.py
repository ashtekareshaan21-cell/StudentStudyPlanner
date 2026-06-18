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

    def __repr__(self):
        return f"<User {self.username}>"
