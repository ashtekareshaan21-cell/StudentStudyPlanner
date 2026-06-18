# test_tasks.py
# Unit and integration tests for Task Management System

import unittest
import json
from app import app, db
from models import User, Task

class TestTaskManagement(unittest.TestCase):

    def setUp(self):
        # Configure app for testing in-memory
        app.config["TESTING"] = True
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()
        
        self.app_context = app.app_context()
        self.app_context.push()
        
        db.create_all()

        # Seed two test users to verify boundaries
        self.test_token_1 = "token_user_1_secret_value"
        self.user1 = User(
            username="user1",
            email="user1@example.com",
            password_hash="hashed_pw_1",
            api_token=self.test_token_1
        )
        self.test_token_2 = "token_user_2_secret_value"
        self.user2 = User(
            username="user2",
            email="user2@example.com",
            password_hash="hashed_pw_2",
            api_token=self.test_token_2
        )
        db.session.add(self.user1)
        db.session.add(self.user2)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_tasks_page_redirects(self):
        # Requires session login
        resp = self.client.get("/tasks")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Please log in to access this page", resp.data)

        # Logged in
        with self.client.session_transaction() as sess:
            sess["user_id"] = self.user1.id
            sess["username"] = self.user1.username
            
        resp = self.client.get("/tasks")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Task Management Board", resp.data)

    def test_get_tasks_list(self):
        # Seed tasks for user1 and user2
        t1 = Task(user_id=self.user1.id, title="User1 Task 1", priority="High", status="Pending")
        t2 = Task(user_id=self.user2.id, title="User2 Task 1", priority="Low", status="Completed")
        db.session.add(t1)
        db.session.add(t2)
        db.session.commit()

        # Request user1 tasks via token
        headers = {"Authorization": f"Bearer {self.test_token_1}"}
        resp = self.client.get("/api/v1/tasks", headers=headers)
        self.assertEqual(resp.status_code, 200)
        
        data = json.loads(resp.data)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["title"], "User1 Task 1")
        self.assertEqual(data[0]["priority"], "High")
        self.assertEqual(data[0]["status"], "Pending")

    def test_create_task(self):
        headers = {
            "Authorization": f"Bearer {self.test_token_1}",
            "Content-Type": "application/json"
        }
        payload = {
            "title": "Study Chemistry Chapter 2",
            "description": "Read organic reactions",
            "priority": "Medium",
            "due_date": "2026-06-25"
        }

        resp = self.client.post("/api/v1/tasks", headers=headers, json=payload)
        self.assertEqual(resp.status_code, 201)
        
        data = json.loads(resp.data)
        self.assertIsNotNone(data["id"])
        self.assertEqual(data["title"], "Study Chemistry Chapter 2")
        self.assertEqual(data["priority"], "Medium")
        self.assertEqual(data["due_date"], "2026-06-25")
        self.assertEqual(data["status"], "Pending")

        # Verify insertion in DB
        db_task = Task.query.filter_by(user_id=self.user1.id).first()
        self.assertIsNotNone(db_task)
        self.assertEqual(db_task.title, "Study Chemistry Chapter 2")

    def test_create_task_validation(self):
        headers = {
            "Authorization": f"Bearer {self.test_token_1}",
            "Content-Type": "application/json"
        }
        
        # Test empty title
        resp = self.client.post("/api/v1/tasks", headers=headers, json={"title": "  "})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.data)["error"], "Task title is required.")

        # Test invalid priority
        resp = self.client.post("/api/v1/tasks", headers=headers, json={"title": "T1", "priority": "Critical"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Priority must be one of", json.loads(resp.data)["error"])

        # Test invalid due date
        resp = self.client.post("/api/v1/tasks", headers=headers, json={"title": "T1", "due_date": "25-06-2026"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid due_date format", json.loads(resp.data)["error"])

    def test_update_task(self):
        # Create a task for user1
        task = Task(user_id=self.user1.id, title="Original Title", priority="Low", status="Pending")
        db.session.add(task)
        db.session.commit()

        # Update task status and title via user1 token
        headers = {
            "Authorization": f"Bearer {self.test_token_1}",
            "Content-Type": "application/json"
        }
        payload = {
            "title": "Updated Title",
            "status": "In Progress",
            "priority": "High"
        }

        resp = self.client.put(f"/api/v1/tasks/{task.id}", headers=headers, json=payload)
        self.assertEqual(resp.status_code, 200)
        
        data = json.loads(resp.data)
        self.assertEqual(data["title"], "Updated Title")
        self.assertEqual(data["status"], "In Progress")
        self.assertEqual(data["priority"], "High")

        # Verify DB updates
        db_task = Task.query.get(task.id)
        self.assertEqual(db_task.title, "Updated Title")
        self.assertEqual(db_task.status, "In Progress")

    def test_update_task_boundary_ownership(self):
        # Create a task for user2
        task = Task(user_id=self.user2.id, title="User2 Task", priority="Low", status="Pending")
        db.session.add(task)
        db.session.commit()

        # Attempt to update user2 task using user1 token
        headers = {
            "Authorization": f"Bearer {self.test_token_1}",
            "Content-Type": "application/json"
        }
        payload = {"status": "Completed"}

        resp = self.client.put(f"/api/v1/tasks/{task.id}", headers=headers, json=payload)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(json.loads(resp.data)["error"], "Task not found.")

        # Task remains unchanged
        db_task = Task.query.get(task.id)
        self.assertEqual(db_task.status, "Pending")

    def test_delete_task(self):
        # Create a task for user1
        task = Task(user_id=self.user1.id, title="To Delete", priority="Low", status="Pending")
        db.session.add(task)
        db.session.commit()

        # Delete task via user1 token
        headers = {"Authorization": f"Bearer {self.test_token_1}"}
        resp = self.client.delete(f"/api/v1/tasks/{task.id}", headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.data)["message"], "Task deleted successfully.")

        # Verify deletion in DB
        db_task = Task.query.get(task.id)
        self.assertIsNull = self.assertIsNone(db_task)

    def test_delete_task_boundary_ownership(self):
        # Create a task for user2
        task = Task(user_id=self.user2.id, title="User2 Task to Delete", priority="Low", status="Pending")
        db.session.add(task)
        db.session.commit()

        # Attempt to delete user2 task using user1 token
        headers = {"Authorization": f"Bearer {self.test_token_1}"}
        resp = self.client.delete(f"/api/v1/tasks/{task.id}", headers=headers)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(json.loads(resp.data)["error"], "Task not found.")

        # Task remains in DB
        db_task = Task.query.get(task.id)
        self.assertIsNotNone(db_task)

if __name__ == '__main__':
    unittest.main()
