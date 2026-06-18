# data_handler.py
# This file handles database operations for storing and retrieving study history using SQLAlchemy models

from datetime import datetime
from models import db, StudySession

def save_study_session(user_id, mood, study_hours, sleep_hours, days_left, subjects, productivity_score, burnout_risk):
    """
    Save a study session to the database using SQLAlchemy.
    """
    try:
        # Accept subjects as list or string
        if isinstance(subjects, list):
            subjects_str = ";".join(subjects)
        else:
            subjects_str = str(subjects)

        new_session = StudySession(
            user_id=user_id,
            session_date=datetime.utcnow(),
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
        print(f"[INFO] Saved study session for user_id={user_id} successfully.")
    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] Failed to save study session: {e}")
        raise e

def get_all_sessions(user_id):
    """
    Read all study sessions for a specific user.
    Returns list of dictionaries to maintain compatibility with CSV output format.
    """
    try:
        rows = StudySession.query.filter_by(user_id=user_id).order_by(StudySession.id.asc()).all()
        sessions = []
        for row in rows:
            sessions.append({
                "Date": row.session_date.strftime("%Y-%m-%d %H:%M:%S"),
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
    Calculate weekly statistics from all sessions
    Returns dictionary with statistics
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
            
            # Parse subjects
            subjects = session['Subjects'].split(';')
            study_hours_per_subject = float(session['Study_Hours']) / len(subjects)
            
            for subject in subjects:
                subject = subject.strip()
                if subject:
                    if subject not in subject_hours:
                        subject_hours[subject] = 0
                    subject_hours[subject] += study_hours_per_subject
        
        except (ValueError, KeyError):
            # Skip rows with invalid data
            continue
    
    session_count = len(sessions)
    
    # Find most studied subject
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
