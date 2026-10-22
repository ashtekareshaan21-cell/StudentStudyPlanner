# data_handler.py
# Handles database session operations and student CSV data logging

import os
import csv
from datetime import datetime, timezone
from models import db, User, StudySession, StudyPlan

# Base Project Root Directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if os.getenv("VERCEL"):
    BASE_DATA_DIR = "/tmp"
else:
    BASE_DATA_DIR = BASE_DIR

DATA_DIR = os.path.join(BASE_DATA_DIR, "data", "students_csv")
MASTER_STUDY_CSV_FILE = os.path.join(BASE_DATA_DIR, "study_data.csv")

try:
    os.makedirs(DATA_DIR, exist_ok=True)
except Exception:
    pass

CSV_FIELDS = [
    "Session_ID",
    "Date",
    "Mood",
    "Study_Hours",
    "Sleep_Hours",
    "Days_Left",
    "Subjects",
    "Productivity_Score",
    "Burnout_Risk",
    "Goal_Type",
    "Study_Mode",
    "Risk_Index"
]

MASTER_STUDY_CSV_FIELDS = [
    "Date",
    "Mood",
    "Study_Hours",
    "Sleep_Hours",
    "Days_Left",
    "Subjects",
    "Productivity_Score",
    "Burnout_Risk",
    "Student_ID",
    "Username"
]


def get_student_csv_path(user_id):
    """
    Returns absolute path to the CSV file of a specific student.
    """
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception:
        pass
    return os.path.join(DATA_DIR, f"student_sessions_{user_id}.csv")


def append_session_to_csv(user_id, row_dict):
    """
    Appends a new study session record to the student's CSV file.
    """
    csv_path = get_student_csv_path(user_id)
    file_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0

    try:
        with open(csv_path, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            if not file_exists:
                writer.writeheader()
            clean_row = {k: row_dict.get(k, "") for k in CSV_FIELDS}
            writer.writerow(clean_row)
    except Exception as e:
        print(f"[WARN] Failed to append to CSV for user {user_id}: {e}")


def append_master_study_session_csv(user_id, username, row_dict):
    """
    Appends a study session to master study_data.csv.
    """
    try:
        file_exists = os.path.exists(MASTER_STUDY_CSV_FILE) and os.path.getsize(MASTER_STUDY_CSV_FILE) > 0
        with open(MASTER_STUDY_CSV_FILE, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=MASTER_STUDY_CSV_FIELDS, extrasaction='ignore')
            if not file_exists:
                writer.writeheader()
            clean_row = {
                "Date": row_dict.get("Date", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                "Mood": row_dict.get("Mood", 3),
                "Study_Hours": row_dict.get("Study_Hours", 2.0),
                "Sleep_Hours": row_dict.get("Sleep_Hours", 7.0),
                "Days_Left": row_dict.get("Days_Left", 7),
                "Subjects": row_dict.get("Subjects", "General"),
                "Productivity_Score": row_dict.get("Productivity_Score", 70.0),
                "Burnout_Risk": row_dict.get("Burnout_Risk", "Low"),
                "Student_ID": user_id,
                "Username": username
            }
            writer.writerow(clean_row)
    except Exception as e:
        print(f"[WARN] Failed appending to master study_data.csv: {e}")


def sync_db_to_csv(user_id):
    """
    Synchronizes study sessions from the database to the student's CSV file.
    """
    csv_path = get_student_csv_path(user_id)
    try:
        sessions = StudySession.query.filter_by(user_id=user_id).order_by(StudySession.id.asc()).all()
        plans = StudyPlan.query.filter_by(user_id=user_id).order_by(StudyPlan.id.asc()).all()

        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()

            for idx, s in enumerate(sessions):
                matching_plan = plans[idx] if idx < len(plans) else None
                goal_val = "University Final Exam"
                mode_val = "Deep Work"
                risk_val = 49

                if matching_plan and matching_plan.plan_details:
                    try:
                        import json
                        det = json.loads(matching_plan.plan_details)
                        goal_val = det.get("goal_label") or det.get("goal_type") or goal_val
                        mode_val = det.get("study_mode_name") or det.get("study_mode") or mode_val
                        risk_val = det.get("risk_index", risk_val)
                    except Exception:
                        pass

                writer.writerow({
                    "Session_ID": s.id,
                    "Date": s.session_date.strftime("%Y-%m-%d %H:%M:%S") if s.session_date else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Mood": s.mood,
                    "Study_Hours": s.study_hours,
                    "Sleep_Hours": s.sleep_hours,
                    "Days_Left": s.days_left,
                    "Subjects": s.subjects,
                    "Productivity_Score": s.productivity_score,
                    "Burnout_Risk": s.burnout_risk,
                    "Goal_Type": goal_val,
                    "Study_Mode": mode_val,
                    "Risk_Index": risk_val
                })
        return csv_path
    except Exception as e:
        print(f"[ERROR] Failed to sync DB to CSV for user {user_id}: {e}")
        return csv_path


def load_student_csv(user_id):
    """
    Reads the student's CSV file and returns list of dictionaries.
    """
    csv_path = get_student_csv_path(user_id)
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        sync_db_to_csv(user_id)

    rows = []
    if not os.path.exists(csv_path):
        return rows

    try:
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(r)
    except Exception as e:
        print(f"[ERROR] Failed to read CSV for user {user_id}: {e}")
    return rows


def save_study_session(user_id, mood, study_hours, sleep_hours, days_left, subjects, productivity_score, burnout_risk, goal_type="University Exam", study_mode="Deep Work", risk_index=49):
    """
    Save a study session to the database AND write it directly to the student's CSV file.
    """
    try:
        subjects_str = ";".join(subjects) if isinstance(subjects, list) else str(subjects)
        now_utc = datetime.now(timezone.utc)
        new_session = StudySession(
            user_id=user_id,
            session_date=now_utc,
            mood=int(mood),
            study_hours=float(study_hours),
            sleep_hours=float(sleep_hours),
            days_left=int(days_left),
            subjects=subjects_str,
            productivity_score=float(productivity_score),
            burnout_risk=str(burnout_risk)
        )
        db.session.add(new_session)
        db.session.commit()

        # Append to individual student CSV file
        append_session_to_csv(user_id, {
            "Session_ID": new_session.id,
            "Date": now_utc.strftime("%Y-%m-%d %H:%M:%S"),
            "Mood": int(mood),
            "Study_Hours": float(study_hours),
            "Sleep_Hours": float(sleep_hours),
            "Days_Left": int(days_left),
            "Subjects": subjects_str,
            "Productivity_Score": float(productivity_score),
            "Burnout_Risk": str(burnout_risk),
            "Goal_Type": goal_type,
            "Study_Mode": study_mode,
            "Risk_Index": risk_index
        })

        # Append to master study_data.csv
        try:
            user = db.session.get(User, user_id)
            uname = user.username if user else f"Student_{user_id}"
            append_master_study_session_csv(user_id, uname, {
                "Date": now_utc.strftime("%Y-%m-%d %H:%M:%S"),
                "Mood": int(mood),
                "Study_Hours": float(study_hours),
                "Sleep_Hours": float(sleep_hours),
                "Days_Left": int(days_left),
                "Subjects": subjects_str,
                "Productivity_Score": float(productivity_score),
                "Burnout_Risk": str(burnout_risk),
                "Student_ID": user_id,
                "Username": uname
            })
        except Exception:
            pass

        return new_session
    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] Failed to save study session: {e}")
        raise e


def update_or_append_student_csv(user_id):
    """
    Lightweight compatibility hook for student activity sync.
    """
    return True


def get_all_sessions(user_id):
    """
    Read all study sessions for a specific user from database.
    """
    try:
        rows = StudySession.query.filter_by(user_id=user_id).order_by(StudySession.id.asc()).all()
        sessions = []
        for row in rows:
            sessions.append({
                "Date": row.session_date.strftime("%Y-%m-%d %H:%M:%S") if row.session_date else "",
                "Mood": str(row.mood),
                "Study_Hours": str(row.study_hours),
                "Sleep_Hours": str(row.sleep_hours),
                "Days_Left": str(row.days_left),
                "Subjects": str(row.subjects),
                "Productivity_Score": str(row.productivity_score),
                "Burnout_Risk": str(row.burnout_risk)
            })
        return sessions
    except Exception as e:
        print(f"[ERROR] Failed to fetch sessions: {e}")
        return []


def calculate_weekly_stats(sessions):
    """
    Calculate summary statistics from sessions.
    """
    if not sessions:
        return {
            "total_sessions": 0,
            "total_study_hours": 0,
            "average_mood": 0,
            "average_sleep": 0,
            "average_productivity": 0,
            "subject_hours": {},
            "most_studied_subject": "None"
        }

    total_study_hours = 0
    total_mood = 0
    total_sleep = 0
    total_productivity = 0
    subject_hours = {}

    for session in sessions:
        try:
            total_study_hours += float(session['Study_Hours'])
            total_mood += int(session['Mood'])
            total_sleep += float(session['Sleep_Hours'])
            total_productivity += float(session['Productivity_Score'])

            subjects = session['Subjects'].split(';')
            study_hours_per_subject = float(session['Study_Hours']) / max(len(subjects), 1)

            for subject in subjects:
                subject = subject.strip()
                if subject:
                    subject_hours[subject] = subject_hours.get(subject, 0) + study_hours_per_subject
        except (ValueError, KeyError):
            continue

    session_count = len(sessions)
    most_studied = "None"
    max_hours = 0
    for subject, hours in subject_hours.items():
        if hours > max_hours:
            max_hours = hours
            most_studied = subject

    return {
        "total_sessions": session_count,
        "total_study_hours": round(total_study_hours, 2),
        "average_mood": round(total_mood / session_count, 2) if session_count > 0 else 0,
        "average_sleep": round(total_sleep / session_count, 2) if session_count > 0 else 0,
        "average_productivity": round(total_productivity / session_count, 2) if session_count > 0 else 0,
        "subject_hours": {subject: round(hours, 2) for subject, hours in subject_hours.items()},
        "most_studied_subject": most_studied
    }
