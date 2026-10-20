# test_python_engine.py
# Unit tests for the Python Engine, CSV Data Handling, and CPPS Academic Showcase

import unittest
import os
from app import app, db
from models import User
from data_handler import (
    initialize_students_csv,
    update_or_append_student_csv,
    sync_all_students_to_csv,
    get_students_csv_rows,
    get_master_study_csv_rows,
    get_csv_file_meta,
    calculate_pure_python_csv_stats,
    get_python_code_metrics,
    STUDENTS_CSV_FILE,
    MASTER_STUDY_CSV_FILE
)


class TestPythonEngineAndCSV(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        with app.app_context():
            db.create_all()

    def test_students_csv_initialization(self):
        """Verify students_data.csv initializes with expected fields and rows."""
        initialize_students_csv()
        self.assertTrue(os.path.exists(STUDENTS_CSV_FILE))
        rows = get_students_csv_rows()
        self.assertGreater(len(rows), 0)
        self.assertIn("Student_ID", rows[0])
        self.assertIn("Username", rows[0])
        self.assertIn("Total_Study_Hours", rows[0])

    def test_csv_file_meta(self):
        """Verify file metadata extraction using pure Python os methods."""
        meta = get_csv_file_meta(STUDENTS_CSV_FILE)
        self.assertTrue(meta["exists"])
        self.assertGreater(meta["size_bytes"], 0)
        self.assertGreater(meta["row_count"], 0)
        self.assertIn("Student_ID", meta["headers"])

    def test_pure_python_csv_stats(self):
        """Verify statistical calculations across student CSV records."""
        stats = calculate_pure_python_csv_stats()
        self.assertGreaterEqual(stats["student_count"], 1)
        self.assertIsInstance(stats["r_sleep_prod"], float)
        self.assertIn("Low", stats["burnout_dist"])

    def test_python_code_metrics(self):
        """Verify code metrics dynamically analyze codebase lines, functions, and classes."""
        metrics = get_python_code_metrics()
        self.assertGreater(metrics["code_lines"], 500)
        self.assertGreater(metrics["total_functions"], 20)
        self.assertGreater(metrics["total_classes"], 4)

    def test_python_engine_page_get(self):
        """Verify /python-engine page renders successfully with status 200."""
        response = self.client.get('/python-engine')
        self.assertEqual(response.status_code, 200)
        content = response.data.decode('utf-8')
        self.assertIn("How Python Powers SmartStudyPlanner", content)
        self.assertIn("Student CSV Data Handling Engine", content)
        self.assertIn("Pearson Correlation", content)

    def test_download_students_csv(self):
        """Verify /download/students-csv endpoint returns text/csv attachment."""
        response = self.client.get('/download/students-csv')
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.content_type)
        self.assertIn("Student_ID", response.data.decode('utf-8'))
        response.close()

    def test_download_sessions_csv(self):
        """Verify /download/sessions-csv endpoint returns text/csv attachment."""
        response = self.client.get('/download/sessions-csv')
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.content_type)
        response.close()

    def test_api_csv_sync(self):
        """Verify /api/csv/sync endpoint returns JSON with success confirmation."""
        response = self.client.post('/api/csv/sync')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("meta", data)

    def test_api_simulate_algorithm(self):
        """Verify interactive Python algorithm simulation trace."""
        response = self.client.post('/api/python/simulate-algorithm', json={
            "mood": 5,
            "study_hours": 4.0,
            "sleep_hours": 8.0,
            "days_left": 3,
            "subjects": "CPPS, Python, Algorithms"
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(len(data.get("python_trace")), 6)
        self.assertIn("productivity_score", data.get("summary"))


if __name__ == '__main__':
    unittest.main()
