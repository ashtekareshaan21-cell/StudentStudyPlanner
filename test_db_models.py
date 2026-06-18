# test_db_models.py
# Unit tests for SQLAlchemy database models and operations

import unittest
import json
from app import app, db
from models import User, StudySession, StudyPlan, QuizResult
from data_handler import save_study_session, get_all_sessions

class TestDatabaseModels(unittest.TestCase):

    def setUp(self):
        # Configure app for testing using in-memory SQLite
        app.config["TESTING"] = True
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["WTF_CSRF_ENABLED"] = False
        
        self.app_context = app.app_context()
        self.app_context.push()
        
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_user_creation(self):
        # Create user
        u = User(username="testuser", email="test@example.com", password_hash="hashed_pw")
        db.session.add(u)
        db.session.commit()
        
        self.assertIsNotNone(u.id)
        self.assertEqual(u.username, "testuser")
        self.assertEqual(u.email, "test@example.com")

    def test_study_session_saving_and_retrieval(self):
        # Create user
        u = User(username="testuser", email="test@example.com", password_hash="hashed_pw")
        db.session.add(u)
        db.session.commit()

        # Save session via data_handler
        save_study_session(
            user_id=u.id,
            mood=4,
            study_hours=3.5,
            sleep_hours=7.0,
            days_left=5,
            subjects=["Math", "Physics"],
            productivity_score=85.0,
            burnout_risk="Low"
        )

        # Retrieve sessions
        sessions = get_all_sessions(u.id)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["Mood"], "4")
        self.assertEqual(sessions[0]["Study_Hours"], "3.5")
        self.assertEqual(sessions[0]["Subjects"], "Math;Physics")

    def test_study_plan_saving(self):
        # Create user
        u = User(username="testuser", email="test@example.com", password_hash="hashed_pw")
        db.session.add(u)
        db.session.commit()

        # Create study plan
        plan = StudyPlan(
            user_id=u.id,
            days_left=3,
            subjects="Programming",
            study_hours=4.0,
            sleep_hours=8.0,
            mood=5,
            productivity_score=95.0,
            burnout_risk="Low",
            plan_details=json.dumps({"breaks": ["1h 0m"], "hours_per_day": 4.0})
        )
        db.session.add(plan)
        db.session.commit()

        retrieved = StudyPlan.query.filter_by(user_id=u.id).first()
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.subjects, "Programming")
        self.assertEqual(json.loads(retrieved.plan_details)["hours_per_day"], 4.0)

    def test_quiz_result_saving(self):
        # Create user
        u = User(username="testuser", email="test@example.com", password_hash="hashed_pw")
        db.session.add(u)
        db.session.commit()

        # Create quiz result
        quiz = QuizResult(
            user_id=u.id,
            topics="Data Structures",
            score=5,
            total_questions=6,
            results_json=json.dumps([{"question": "Q1", "is_correct": True}])
        )
        db.session.add(quiz)
        db.session.commit()

        retrieved = QuizResult.query.filter_by(user_id=u.id).first()
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.score, 5)
        self.assertEqual(retrieved.topics, "Data Structures")

if __name__ == '__main__':
    unittest.main()
