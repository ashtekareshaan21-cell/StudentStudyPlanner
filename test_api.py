# test_api.py
# Integration tests for RESTful API v1 endpoints

import unittest
import json
from app import app, db
from models import User, StudySession, StudyPlan, QuizResult

class TestRestAPI(unittest.TestCase):

    def setUp(self):
        # Configure app for testing in-memory
        app.config["TESTING"] = True
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()
        
        self.app_context = app.app_context()
        self.app_context.push()
        
        db.create_all()

        # Seed a test user
        self.test_username = "apitester"
        self.test_email = "api@example.com"
        self.test_token = "abcd1234efgh5678ijkl9012"
        self.user = User(
            username=self.test_username,
            email=self.test_email,
            password_hash="hashed_pw",
            api_token=self.test_token
        )
        db.session.add(self.user)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_unauthorized_endpoints(self):
        # Verify requests without credentials fail with 401
        endpoints = [
            ("/api/v1/sessions", "GET"),
            ("/api/v1/sessions", "POST"),
            ("/api/v1/plans", "GET"),
            ("/api/v1/quiz-results", "GET")
        ]
        
        for url, method in endpoints:
            if method == "GET":
                resp = self.client.get(url)
            else:
                resp = self.client.post(url, json={})
                
            self.assertEqual(resp.status_code, 401)
            data = json.loads(resp.data)
            self.assertIn("error", data)
            self.assertEqual(data["error"], "Unauthorized. Please log in or provide a valid API token.")

    def test_get_api_token_endpoint(self):
        # Requesting /api/v1/token without logging in redirect/fail
        resp = self.client.get("/api/v1/token")
        # Standard web routes redirect/render login page for browser session guards
        self.assertEqual(resp.status_code, 200) # Wait, login_required decorator renders login.html directly (200 OK)
        self.assertIn(b"Please log in to access this page", resp.data)

        # Access with session log in
        with self.client.session_transaction() as sess:
            sess["user_id"] = self.user.id
            sess["username"] = self.user.username
            
        resp = self.client.get("/api/v1/token")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["api_token"], self.test_token)

    def test_get_sessions_via_token(self):
        # Add a test session
        session_row = StudySession(
            user_id=self.user.id,
            mood=4,
            study_hours=3.0,
            sleep_hours=7.5,
            days_left=4,
            subjects="Programming;Math",
            productivity_score=80.0,
            burnout_risk="Low"
        )
        db.session.add(session_row)
        db.session.commit()

        # Call API using valid token
        headers = {"Authorization": f"Bearer {self.test_token}"}
        resp = self.client.get("/api/v1/sessions", headers=headers)
        self.assertEqual(resp.status_code, 200)
        
        data = json.loads(resp.data)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["mood"], 4)
        self.assertEqual(data[0]["study_hours"], 3.0)
        self.assertEqual(data[0]["subjects"], ["Programming", "Math"])

    def test_post_session_via_token_success(self):
        headers = {
            "Authorization": f"Bearer {self.test_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "mood": 5,
            "study_hours": 4.5,
            "sleep_hours": 8.0,
            "days_left": 10,
            "subjects": ["Physics", "Chemistry"],
            "productivity_score": 98.0,
            "burnout_risk": "None"
        }

        resp = self.client.post("/api/v1/sessions", headers=headers, json=payload)
        self.assertEqual(resp.status_code, 201)
        
        data = json.loads(resp.data)
        self.assertEqual(data["mood"], 5)
        self.assertEqual(data["study_hours"], 4.5)
        self.assertEqual(data["subjects"], ["Physics", "Chemistry"])
        self.assertEqual(data["productivity_score"], 98.0)

        # Verify it was persisted
        db_records = StudySession.query.filter_by(user_id=self.user.id).all()
        self.assertEqual(len(db_records), 1)
        self.assertEqual(db_records[0].mood, 5)

    def test_post_session_invalid_input(self):
        headers = {
            "Authorization": f"Bearer {self.test_token}",
            "Content-Type": "application/json"
        }
        
        # Test invalid mood
        resp = self.client.post("/api/v1/sessions", headers=headers, json={"mood": 6})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Mood must be an integer between 1 and 5", json.loads(resp.data)["error"])

        # Test negative hours
        resp = self.client.post("/api/v1/sessions", headers=headers, json={"study_hours": -1.0})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("must be non-negative", json.loads(resp.data)["error"])

    def test_post_session_dynamic_calculation(self):
        headers = {
            "Authorization": f"Bearer {self.test_token}",
            "Content-Type": "application/json"
        }
        # Payload missing productivity_score and burnout_risk
        payload = {
            "mood": 4,
            "study_hours": 2.0,
            "sleep_hours": 7.0,
            "days_left": 5,
            "subjects": ["General"]
        }

        resp = self.client.post("/api/v1/sessions", headers=headers, json=payload)
        self.assertEqual(resp.status_code, 201)
        
        data = json.loads(resp.data)
        # Should be calculated dynamically by analyzer
        self.assertIsNotNone(data["productivity_score"])
        self.assertIsNotNone(data["burnout_risk"])

    def test_get_plans_via_token(self):
        plan_row = StudyPlan(
            user_id=self.user.id,
            days_left=3,
            subjects="Math",
            study_hours=2.0,
            sleep_hours=7.0,
            mood=3,
            productivity_score=75.0,
            burnout_risk="Low",
            plan_details=json.dumps({"breaks": ["1h"], "hours_per_day": 2.0})
        )
        db.session.add(plan_row)
        db.session.commit()

        headers = {"Authorization": f"Bearer {self.test_token}"}
        resp = self.client.get("/api/v1/plans", headers=headers)
        self.assertEqual(resp.status_code, 200)
        
        data = json.loads(resp.data)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["plan_details"]["hours_per_day"], 2.0)

    def test_get_and_delete_single_plan_via_token(self):
        plan_row = StudyPlan(
            user_id=self.user.id,
            days_left=5,
            subjects="Codex",
            study_hours=5.0,
            sleep_hours=7.0,
            mood=4,
            productivity_score=80.0,
            burnout_risk="Low",
            plan_details=json.dumps({"blocks": [{"title": "Deep work — Codex"}]})
        )
        db.session.add(plan_row)
        db.session.commit()

        headers = {"Authorization": f"Bearer {self.test_token}"}
        
        # Test GET single plan
        resp = self.client.get(f"/api/v1/plans/{plan_row.id}", headers=headers)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["subjects"], ["Codex"])

        # Test DELETE single plan
        del_resp = self.client.delete(f"/api/v1/plans/{plan_row.id}", headers=headers)
        self.assertEqual(del_resp.status_code, 200)
        self.assertIn("deleted successfully", json.loads(del_resp.data)["message"])

        # Confirm 404 after deletion
        get_again = self.client.get(f"/api/v1/plans/{plan_row.id}", headers=headers)
        self.assertEqual(get_again.status_code, 404)

    def test_get_quiz_results_via_token(self):
        quiz_row = QuizResult(
            user_id=self.user.id,
            topics="Sorting",
            score=4,
            total_questions=5,
            results_json=json.dumps([{"q": "Q1", "user": "A", "correct": "A"}])
        )
        db.session.add(quiz_row)
        db.session.commit()

        headers = {"Authorization": f"Bearer {self.test_token}"}
        resp = self.client.get("/api/v1/quiz-results", headers=headers)
        self.assertEqual(resp.status_code, 200)
        
        data = json.loads(resp.data)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["topics"], "Sorting")
        self.assertEqual(data[0]["score"], 4)
        self.assertEqual(data[0]["results"][0]["q"], "Q1")

    def test_docs_routes(self):
        # /docs should redirect to /docs/swagger
        resp = self.client.get("/docs")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/docs/swagger", resp.location)

        # /docs/swagger should return 200 and Swagger UI markup
        resp_swagger = self.client.get("/docs/swagger")
        self.assertEqual(resp_swagger.status_code, 200)
        self.assertIn(b"swagger-ui", resp_swagger.data)
        self.assertIn(b"swagger_init.js", resp_swagger.data)

        # /docs/redoc should return 200 and ReDoc markup
        resp_redoc = self.client.get("/docs/redoc")
        self.assertEqual(resp_redoc.status_code, 200)
        self.assertIn(b"redoc", resp_redoc.data)
        self.assertIn(b"openapi.json", resp_redoc.data)

if __name__ == '__main__':
    unittest.main()

