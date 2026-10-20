# test_planner_personalisation.py
import unittest
from app import app, db
from models import User, StudyPlan
from study_planner import generate_study_plan, generate_schedule_blocks, get_goal_recommendations, STUDY_MODES, GOAL_TYPES

class TestPersonalisationFeatures(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Seed user
        self.user = User(
            username="testuser",
            email="testuser@example.com",
            password_hash="pw123",
            api_token="test_token_123"
        )
        db.session.add(self.user)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_goal_recommendations(self):
        # Check all goal types produce meaningful recommendations
        for goal_key, label in GOAL_TYPES.items():
            recs = get_goal_recommendations(goal_key, weak_subjects=["Data Structures"])
            self.assertTrue(len(recs) >= 3, f"Goal {goal_key} should have at least 3 recommendations")
            # When weak subject is passed, at least one recommendation should highlight it
            found_weak = any("Data Structures" in r for r in recs)
            self.assertTrue(found_weak, f"Expected weak subject in recommendations for {goal_key}")

    def test_study_mode_intervals(self):
        plan_pomo = generate_study_plan(mood_score=4, study_hours=4.0, days_left=7, subjects=["Math"], sleep_hours=7.0, study_mode="pomodoro")
        self.assertEqual(plan_pomo["focus_block_mins"], 25)
        self.assertEqual(plan_pomo["short_break_mins"], 5)
        self.assertEqual(plan_pomo["long_break_mins"], 15)

        plan_ultra = generate_study_plan(mood_score=4, study_hours=6.0, days_left=7, subjects=["Math"], sleep_hours=7.0, study_mode="ultradian")
        self.assertEqual(plan_ultra["focus_block_mins"], 90)
        self.assertEqual(plan_ultra["short_break_mins"], 20)
        self.assertEqual(plan_ultra["long_break_mins"], 30)

    def test_weak_subject_priority_slot(self):
        # OS is normal, Compiler is weak
        subjects = [
            {"name": "OS", "days_left": 10, "complexity": 3, "is_weak": False},
            {"name": "Compiler", "days_left": 10, "complexity": 3, "is_weak": True}
        ]
        schedule = generate_schedule_blocks(start_time="09:00", subjects=subjects, study_hours=4.0, mood=4, sleep_hours=8.0)
        focus_blocks = [b for b in schedule["blocks"] if b["type"] == "focus"]
        self.assertTrue(len(focus_blocks) >= 2)
        # First focus block must be the weak subject "Compiler"
        self.assertIn("Compiler", focus_blocks[0]["title"])

    def test_api_generate_plan_personalisation(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["username"] = "testuser"
            sess["csrf_token"] = "test_token"

        payload = {
            "mood": 4,
            "sleep_hours": 7.5,
            "start_time": "08:00",
            "study_hours": 4.5,
            "goal_type": "placement",
            "study_mode": "pomodoro",
            "preferred_time": "morning",
            "csrf_token": "test_token",
            "subjects": [
                {"name": "Python", "days_left": 5, "complexity": 3, "topics": "Decorators, OOP", "is_weak": True},
                {"name": "SQL", "days_left": 14, "complexity": 2, "topics": "Joins, Indexes", "is_weak": False}
            ]
        }

        res = self.client.post("/generate-plan", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["goal_type"], "placement")
        self.assertEqual(data["study_mode"], "pomodoro")
        self.assertTrue(len(data["blocks"]) > 0)

        # Check HTML render route as well
        form_data = {
            "mood": "4",
            "sleep_hours": "7.0",
            "start_time": "18:00",
            "study_hours": "5.0",
            "goal_type": "placement",
            "study_mode": "deep_work",
            "csrf_token": "test_token",
            "subject_name[]": ["Data Structures", "Web Dev"],
            "days_left[]": ["5", "10"],
            "complexity[]": ["4", "2"],
            "topics[]": ["Trees", "CSS"],
            "is_weak[]": ["true", "false"]
        }
        res_form = self.client.post("/generate-plan", data=form_data)
        self.assertEqual(res_form.status_code, 200)
        html_content = res_form.get_data(as_text=True)
        self.assertIn("Placement &amp; Coding Prep", html_content)
        self.assertIn("Deep Work", html_content)
        self.assertIn("Priority", html_content)

if __name__ == "__main__":
    unittest.main()
