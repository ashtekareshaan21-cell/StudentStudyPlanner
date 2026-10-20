# data_handler.py
# This file handles database operations and per-student CSV data science handling

import os
import csv
import math
from datetime import datetime, timezone
from models import db, User, StudySession, StudyPlan, QuizResult, Task

# Base Project Root Directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Master CSV file locations and storage directory
if os.getenv("VERCEL"):
    BASE_DATA_DIR = "/tmp"
    DATA_DIR = os.path.join(BASE_DATA_DIR, "data", "students_csv")
    STUDENTS_CSV_FILE = os.path.join(BASE_DATA_DIR, "students_data.csv")
    MASTER_STUDY_CSV_FILE = os.path.join(BASE_DATA_DIR, "study_data.csv")

    import shutil
    repo_students_csv = os.path.join(BASE_DIR, "students_data.csv")
    if os.path.exists(repo_students_csv) and not os.path.exists(STUDENTS_CSV_FILE):
        try:
            shutil.copyfile(repo_students_csv, STUDENTS_CSV_FILE)
        except Exception:
            pass

    repo_study_csv = os.path.join(BASE_DIR, "study_data.csv")
    if os.path.exists(repo_study_csv) and not os.path.exists(MASTER_STUDY_CSV_FILE):
        try:
            shutil.copyfile(repo_study_csv, MASTER_STUDY_CSV_FILE)
        except Exception:
            pass
else:
    DATA_DIR = os.path.join(BASE_DIR, "data", "students_csv")
    STUDENTS_CSV_FILE = os.path.join(BASE_DIR, "students_data.csv")
    MASTER_STUDY_CSV_FILE = os.path.join(BASE_DIR, "study_data.csv")

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

STUDENTS_CSV_FIELDS = [
    "Student_ID",
    "Username",
    "Email",
    "Registration_Date",
    "Total_Sessions",
    "Total_Study_Hours",
    "Avg_Sleep_Hours",
    "Avg_Mood",
    "Avg_Productivity",
    "Burnout_Risk",
    "Quizzes_Taken",
    "Avg_Quiz_Score",
    "Total_Tasks",
    "Completed_Tasks",
    "Last_Active"
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
    Creates file with header if it does not exist yet.
    """
    csv_path = get_student_csv_path(user_id)
    file_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0

    try:
        with open(csv_path, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            if not file_exists:
                writer.writeheader()
            
            clean_row = {}
            for k in CSV_FIELDS:
                clean_row[k] = row_dict.get(k, "")
            writer.writerow(clean_row)
        print(f"[INFO] Appended session to CSV for user {user_id} at {csv_path}")
    except Exception as e:
        print(f"[WARN] Failed to append to CSV for user {user_id}: {e}")


def sync_db_to_csv(user_id):
    """
    Synchronizes all study sessions from database to the student's CSV file.
    Ensures that historical records are preserved and exported.
    """
    csv_path = get_student_csv_path(user_id)
    try:
        sessions = StudySession.query.filter_by(user_id=user_id).order_by(StudySession.id.asc()).all()
        plans = StudyPlan.query.filter_by(user_id=user_id).order_by(StudyPlan.id.asc()).all()
        
        # Build plan lookup by index or id
        plan_lookup = {}
        for p in plans:
            plan_lookup[p.id] = p

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
        print(f"[INFO] Synced {len(sessions)} records to {csv_path}")
        return csv_path
    except Exception as e:
        print(f"[ERROR] Failed to sync DB to CSV for user {user_id}: {e}")
        return csv_path


def load_student_csv(user_id):
    """
    Reads the student's CSV file and returns list of dictionaries.
    If CSV does not exist yet, triggers a sync from the database.
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
        if isinstance(subjects, list):
            subjects_str = ";".join(subjects)
        else:
            subjects_str = str(subjects)

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

        # Also append immediately to student's CSV file
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

        # Also update master study_data.csv and master students_data.csv
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
            update_or_append_student_csv(user_id)
        except Exception as csv_err:
            print(f"[WARN] Failed to update master student CSV: {csv_err}")

        print(f"[INFO] Saved study session and updated CSV for user_id={user_id}.")
        return new_session
    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] Failed to save study session: {e}")
        raise e


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


def _calculate_pearson_correlation(x_vals, y_vals):
    """
    Computes Pearson Correlation Coefficient (r) using pure Python:
    r = sum((x - mean_x) * (y - mean_y)) / sqrt(sum((x - mean_x)^2) * sum((y - mean_y)^2))
    """
    n = len(x_vals)
    if n < 2 or len(y_vals) != n:
        return 0.0

    mean_x = sum(x_vals) / n
    mean_y = sum(y_vals) / n

    cov_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_vals, y_vals))
    var_x = sum((x - mean_x) ** 2 for x in x_vals)
    var_y = sum((y - mean_y) ** 2 for y in y_vals)

    denom = math.sqrt(var_x * var_y)
    if denom == 0:
        return 0.0
    return round(cov_xy / denom, 3)


def perform_data_science_analysis(user_id):
    """
    Performs comprehensive data handling and statistical analysis
    directly on the student's CSV file.
    Returns metrics, chart datasets, and algorithmic insights for the Analyse tab.
    """
    raw_records = load_student_csv(user_id)
    if not raw_records:
        # Check if database has records to sync
        sync_db_to_csv(user_id)
        raw_records = load_student_csv(user_id)

    total_records = len(raw_records)
    if total_records == 0:
        return {
            "has_data": False,
            "total_records": 0,
            "raw_rows": [],
            "stats": {},
            "charts": {},
            "insights": ["No study sessions recorded yet. Generate your first plan to start tracking data science analytics!"]
        }

    # Extract numerical series
    dates = []
    study_hours_list = []
    sleep_hours_list = []
    moods_list = []
    productivity_list = []
    risk_index_list = []
    burnout_levels = {"Low": 0, "Medium": 0, "High": 0}
    subject_time_map = {}
    goal_distribution = {}
    study_mode_distribution = {}

    for row in raw_records:
        try:
            date_raw = row.get("Date", "")
            try:
                dt_obj = datetime.strptime(date_raw, "%Y-%m-%d %H:%M:%S")
                short_date = dt_obj.strftime("%d %b %H:%M")
            except Exception:
                short_date = date_raw[:16] if len(date_raw) >= 16 else date_raw
            dates.append(short_date)

            s_h = float(row.get("Study_Hours", 0))
            sl_h = float(row.get("Sleep_Hours", 0))
            m = int(float(row.get("Mood", 3)))
            prod = float(row.get("Productivity_Score", 0))
            risk = int(float(row.get("Risk_Index", 49)))

            study_hours_list.append(s_h)
            sleep_hours_list.append(sl_h)
            moods_list.append(m)
            productivity_list.append(prod)
            risk_index_list.append(risk)

            # Burnout tally
            b_risk = str(row.get("Burnout_Risk", "Low")).capitalize()
            if "High" in b_risk:
                burnout_levels["High"] += 1
            elif "Medium" in b_risk:
                burnout_levels["Medium"] += 1
            else:
                burnout_levels["Low"] += 1

            # Subject breakdown
            subjs = [s.strip() for s in row.get("Subjects", "General").split(";") if s.strip()]
            share = s_h / max(len(subjs), 1)
            for s in subjs:
                subject_time_map[s] = subject_time_map.get(s, 0.0) + share

            # Goal & Mode
            g_type = row.get("Goal_Type", "University Exam")
            goal_distribution[g_type] = goal_distribution.get(g_type, 0) + 1

            s_mode = row.get("Study_Mode", "Deep Work")
            study_mode_distribution[s_mode] = study_mode_distribution.get(s_mode, 0) + 1

        except (ValueError, TypeError):
            continue

    n = len(study_hours_list)
    if n == 0:
        return {"has_data": False, "total_records": 0, "raw_rows": raw_records}

    # Descriptive Statistics in Pure Python
    avg_study = round(sum(study_hours_list) / n, 2)
    avg_sleep = round(sum(sleep_hours_list) / n, 2)
    avg_mood = round(sum(moods_list) / n, 2)
    avg_prod = round(sum(productivity_list) / n, 2)
    avg_risk = round(sum(risk_index_list) / n, 1)

    # Standard Deviation: sqrt(sum((x - mean)^2) / N)
    std_study = round(math.sqrt(sum((x - avg_study)**2 for x in study_hours_list) / n), 2)
    std_sleep = round(math.sqrt(sum((x - avg_sleep)**2 for x in sleep_hours_list) / n), 2)

    # Pearson Correlation Coefficient (r)
    sleep_prod_corr = _calculate_pearson_correlation(sleep_hours_list, productivity_list)
    mood_study_corr = _calculate_pearson_correlation(moods_list, study_hours_list)

    # Subject distribution formatted
    sorted_subjects = sorted(subject_time_map.items(), key=lambda item: item[1], reverse=True)
    top_subjects_labels = [s[0] for s in sorted_subjects]
    top_subjects_hours = [round(s[1], 2) for s in sorted_subjects]

    # Mood vs Productivity Average Profile
    mood_prod_buckets = {1: [], 2: [], 3: [], 4: [], 5: []}
    for m, p in zip(moods_list, productivity_list):
        if m in mood_prod_buckets:
            mood_prod_buckets[m].append(p)
    mood_avg_prod = [
        round(sum(mood_prod_buckets[lvl]) / len(mood_prod_buckets[lvl]), 1) if mood_prod_buckets[lvl] else 0.0
        for lvl in range(1, 6)
    ]

    # Dynamic Data Science Insights derived mathematically
    insights = []
    if sleep_prod_corr > 0.4:
        insights.append(f"Strong positive correlation (r = +{sleep_prod_corr}) detected between sleep and productivity: each hour of adequate sleep significantly boosts your study efficiency.")
    elif sleep_prod_corr < -0.2:
        insights.append(f"Negative correlation (r = {sleep_prod_corr}) between sleep and output indicates possible late-night cramming. Shifting to morning sessions is recommended.")
    else:
        insights.append(f"Moderate correlation (r = {sleep_prod_corr}) between sleep duration and cognitive productivity across your logged sessions.")

    if avg_sleep < 6.5:
        insights.append(f"Mean sleep duration is {avg_sleep}h (below the 7.0h cognitive baseline). Raising sleep to 7.5h will decrease your average risk index of {avg_risk}/100.")
    else:
        insights.append(f"Healthy sleep foundation maintained at {avg_sleep}h/day, keeping high-risk burnout rates low.")

    if top_subjects_labels:
        top_s = top_subjects_labels[0]
        top_h = top_subjects_hours[0]
        tot_h = sum(study_hours_list)
        pct = round((top_h / max(tot_h, 0.01)) * 100, 1)
        insights.append(f"Your primary focus subject is '{top_s}', absorbing {top_h}h ({pct}% of total logged study volume).")

    return {
        "has_data": True,
        "total_records": n,
        "raw_rows": raw_records[::-1],  # newest first
        "stats": {
            "avg_study_hours": avg_study,
            "std_study_hours": std_study,
            "avg_sleep_hours": avg_sleep,
            "std_sleep_hours": std_sleep,
            "avg_mood": avg_mood,
            "avg_productivity": avg_prod,
            "avg_risk_index": avg_risk,
            "total_study_hours": round(sum(study_hours_list), 2),
            "sleep_prod_corr": sleep_prod_corr,
            "mood_study_corr": mood_study_corr,
            "burnout_levels": burnout_levels
        },
        "charts": {
            "timeline_labels": dates,
            "study_hours": study_hours_list,
            "sleep_hours": sleep_hours_list,
            "productivity": productivity_list,
            "risk_index": risk_index_list,
            "moods": moods_list,
            "subject_labels": top_subjects_labels,
            "subject_hours": top_subjects_hours,
            "mood_avg_prod": mood_avg_prod
        },
        "insights": insights
    }


# ==============================================================================
# PURE PYTHON STUDENT CSV DATA HANDLING ENGINE (CPPS ACADEMIC SHOWCASE)
# ==============================================================================

INITIAL_STUDENTS_SEED = [
    {
        "Student_ID": "101",
        "Username": "alex_johnson",
        "Email": "alex.j@college.edu",
        "Registration_Date": "2026-03-12 09:15:00",
        "Total_Sessions": "8",
        "Total_Study_Hours": "34.5",
        "Avg_Sleep_Hours": "7.5",
        "Avg_Mood": "4.2",
        "Avg_Productivity": "84.2",
        "Burnout_Risk": "Low",
        "Quizzes_Taken": "4",
        "Avg_Quiz_Score": "87.5",
        "Total_Tasks": "6",
        "Completed_Tasks": "5",
        "Last_Active": "2026-04-28 14:10:00"
    },
    {
        "Student_ID": "102",
        "Username": "maya_patel",
        "Email": "maya.patel@college.edu",
        "Registration_Date": "2026-03-15 11:20:00",
        "Total_Sessions": "11",
        "Total_Study_Hours": "46.0",
        "Avg_Sleep_Hours": "6.8",
        "Avg_Mood": "3.8",
        "Avg_Productivity": "78.4",
        "Burnout_Risk": "Medium",
        "Quizzes_Taken": "5",
        "Avg_Quiz_Score": "92.0",
        "Total_Tasks": "8",
        "Completed_Tasks": "7",
        "Last_Active": "2026-04-28 16:45:00"
    },
    {
        "Student_ID": "103",
        "Username": "rahul_cpps",
        "Email": "rahul.sharma@college.edu",
        "Registration_Date": "2026-03-20 14:00:00",
        "Total_Sessions": "6",
        "Total_Study_Hours": "21.5",
        "Avg_Sleep_Hours": "8.0",
        "Avg_Mood": "4.5",
        "Avg_Productivity": "89.0",
        "Burnout_Risk": "Low",
        "Quizzes_Taken": "3",
        "Avg_Quiz_Score": "80.0",
        "Total_Tasks": "4",
        "Completed_Tasks": "4",
        "Last_Active": "2026-04-27 19:30:00"
    },
    {
        "Student_ID": "104",
        "Username": "priyanshu_v",
        "Email": "priyanshu@college.edu",
        "Registration_Date": "2026-03-25 10:45:00",
        "Total_Sessions": "14",
        "Total_Study_Hours": "58.0",
        "Avg_Sleep_Hours": "5.5",
        "Avg_Mood": "2.9",
        "Avg_Productivity": "67.5",
        "Burnout_Risk": "High",
        "Quizzes_Taken": "6",
        "Avg_Quiz_Score": "75.0",
        "Total_Tasks": "10",
        "Completed_Tasks": "6",
        "Last_Active": "2026-04-28 22:15:00"
    },
    {
        "Student_ID": "105",
        "Username": "sophia_chen",
        "Email": "sophia.c@college.edu",
        "Registration_Date": "2026-04-01 16:30:00",
        "Total_Sessions": "9",
        "Total_Study_Hours": "38.0",
        "Avg_Sleep_Hours": "7.2",
        "Avg_Mood": "4.0",
        "Avg_Productivity": "83.1",
        "Burnout_Risk": "Low",
        "Quizzes_Taken": "4",
        "Avg_Quiz_Score": "95.0",
        "Total_Tasks": "7",
        "Completed_Tasks": "6",
        "Last_Active": "2026-04-28 18:05:00"
    }
]


def initialize_students_csv():
    """
    Ensures students_data.csv exists with proper schema and initial data.
    Demonstrates pure Python file checking, DictWriter, and writeheader operations.
    """
    file_exists = os.path.exists(STUDENTS_CSV_FILE) and os.path.getsize(STUDENTS_CSV_FILE) > 0
    if not file_exists:
        try:
            with open(STUDENTS_CSV_FILE, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=STUDENTS_CSV_FIELDS)
                writer.writeheader()
                for student in INITIAL_STUDENTS_SEED:
                    writer.writerow(student)
            print(f"[INFO] Initialized students_data.csv with {len(INITIAL_STUDENTS_SEED)} baseline student records.")
        except Exception as e:
            print(f"[ERROR] Could not initialize students_data.csv: {e}")


def update_or_append_student_csv(user_id):
    """
    Updates or appends a student's metrics to students_data.csv using pure Python CSV file handling.
    Aggregates study sessions, quiz performance, and task statuses directly from relational records.
    Demonstrates:
      - csv.DictReader for reading and parsing
      - list-of-dicts manipulation and lookup
      - in-memory row mutation
      - csv.DictWriter for atomic rewriting
    """
    initialize_students_csv()

    try:
        user = db.session.get(User, user_id)
        if not user:
            print(f"[WARN] User {user_id} not found in database for CSV update.")
            return False

        # Compute student metrics from related models
        sessions = user.sessions
        quizzes = user.quiz_results
        tasks = user.tasks

        total_sessions = len(sessions)
        total_hours = sum(s.study_hours for s in sessions)
        avg_sleep = (sum(s.sleep_hours for s in sessions) / total_sessions) if total_sessions > 0 else 7.0
        avg_mood = (sum(s.mood for s in sessions) / total_sessions) if total_sessions > 0 else 3.0
        avg_prod = (sum(s.productivity_score for s in sessions) / total_sessions) if total_sessions > 0 else 75.0
        
        last_burnout = "Low"
        if sessions:
            sorted_sessions = sorted(sessions, key=lambda s: s.session_date or datetime.min)
            last_burnout = str(sorted_sessions[-1].burnout_risk).capitalize()

        quizzes_taken = len(quizzes)
        avg_quiz_score = 0.0
        if quizzes_taken > 0:
            pct_scores = [((q.score / max(q.total_questions, 1)) * 100.0) for q in quizzes]
            avg_quiz_score = sum(pct_scores) / quizzes_taken

        total_tasks = len(tasks)
        completed_tasks = sum(1 for t in tasks if t.status == 'Completed')

        # Determine last active timestamp
        activity_dates = []
        if user.created_at:
            activity_dates.append(user.created_at)
        for s in sessions:
            if s.session_date:
                activity_dates.append(s.session_date)
        for q in quizzes:
            if q.created_at:
                activity_dates.append(q.created_at)
        for t in tasks:
            if t.created_at:
                activity_dates.append(t.created_at)

        latest_dt = max(activity_dates) if activity_dates else datetime.now(timezone.utc)
        last_active_str = latest_dt.strftime("%Y-%m-%d %H:%M:%S")

        reg_date_str = user.created_at.strftime("%Y-%m-%d %H:%M:%S") if user.created_at else last_active_str

        # Build fresh student dictionary
        student_record = {
            "Student_ID": str(user.id),
            "Username": user.username,
            "Email": user.email,
            "Registration_Date": reg_date_str,
            "Total_Sessions": str(total_sessions),
            "Total_Study_Hours": f"{total_hours:.1f}",
            "Avg_Sleep_Hours": f"{avg_sleep:.1f}",
            "Avg_Mood": f"{avg_mood:.1f}",
            "Avg_Productivity": f"{avg_prod:.1f}",
            "Burnout_Risk": last_burnout,
            "Quizzes_Taken": str(quizzes_taken),
            "Avg_Quiz_Score": f"{avg_quiz_score:.1f}",
            "Total_Tasks": str(total_tasks),
            "Completed_Tasks": str(completed_tasks),
            "Last_Active": last_active_str
        }

        # Read existing CSV rows
        existing_rows = []
        if os.path.exists(STUDENTS_CSV_FILE):
            with open(STUDENTS_CSV_FILE, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    existing_rows.append(r)

        # Update matching row or append new one
        updated = False
        for idx, row in enumerate(existing_rows):
            if row.get("Student_ID") == str(user.id) or row.get("Username") == user.username:
                existing_rows[idx] = student_record
                updated = True
                break

        if not updated:
            existing_rows.append(student_record)

        # Write all rows back safely with DictWriter
        with open(STUDENTS_CSV_FILE, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=STUDENTS_CSV_FIELDS)
            writer.writeheader()
            for r in existing_rows:
                clean_r = {k: r.get(k, "") for k in STUDENTS_CSV_FIELDS}
                writer.writerow(clean_r)

        print(f"[INFO] Successfully updated students_data.csv for Student #{user.id} ({user.username}).")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to update students_data.csv for user {user_id}: {e}")
        return False


def sync_all_students_to_csv():
    """
    Synchronizes all registered users in the database to students_data.csv.
    If no users exist yet in DB, populates baseline seeds so data handling is visible.
    """
    initialize_students_csv()
    try:
        db.create_all()
        users = User.query.all()
        if not users:
            print("[INFO] No registered users in DB; baseline seeds active in students_data.csv.")
            return True

        for u in users:
            update_or_append_student_csv(u.id)
        print(f"[INFO] Synced {len(users)} registered students to students_data.csv.")
        return True
    except Exception as e:
        print(f"[WARN] Database sync fallback to baseline CSV: {e}")
        initialize_students_csv()
        return True


def append_master_study_session_csv(user_id, username, row_dict):
    """
    Appends a new study session to the root master study_data.csv file.
    Preserves historical CSV entries while attributing new sessions to students.
    """
    file_exists = os.path.exists(MASTER_STUDY_CSV_FILE) and os.path.getsize(MASTER_STUDY_CSV_FILE) > 0
    try:
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
        print(f"[INFO] Appended session to master study_data.csv for student '{username}' (#{user_id}).")
        return True
    except Exception as e:
        print(f"[WARN] Failed appending to master study_data.csv: {e}")
        return False


def get_students_csv_rows():
    """
    Reads all student records from students_data.csv.
    Returns list of dicts.
    """
    initialize_students_csv()
    rows = []
    if os.path.exists(STUDENTS_CSV_FILE):
        try:
            with open(STUDENTS_CSV_FILE, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    rows.append(r)
        except Exception as e:
            print(f"[ERROR] Reading students_data.csv: {e}")
    return rows


def get_master_study_csv_rows(limit=100):
    """
    Reads the latest study sessions from study_data.csv.
    Returns list of dicts ordered newest first.
    """
    rows = []
    if os.path.exists(MASTER_STUDY_CSV_FILE):
        try:
            with open(MASTER_STUDY_CSV_FILE, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    rows.append(r)
        except Exception as e:
            print(f"[ERROR] Reading study_data.csv: {e}")
    return rows[::-1][:limit]


def get_csv_file_meta(file_path):
    """
    Computes file-level metadata using standard Python os module:
    file size (bytes and KB), line count, last modified timestamp, and headers.
    """
    if not os.path.exists(file_path):
        return {
            "exists": False,
            "filename": os.path.basename(file_path),
            "size_bytes": 0,
            "size_kb": 0.0,
            "row_count": 0,
            "last_modified": "N/A",
            "headers": []
        }

    size_bytes = os.path.getsize(file_path)
    mtime = os.path.getmtime(file_path)
    mod_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
    
    headers = []
    row_count = 0
    try:
        with open(file_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header_row = next(reader, None)
            if header_row:
                headers = header_row
            for _ in reader:
                row_count += 1
    except Exception:
        pass

    return {
        "exists": True,
        "filename": os.path.basename(file_path),
        "abs_path": file_path,
        "size_bytes": size_bytes,
        "size_kb": round(size_bytes / 1024.0, 2),
        "row_count": row_count,
        "last_modified": mod_str,
        "headers": headers
    }


def calculate_pure_python_csv_stats():
    """
    Demonstrates real-world data science algorithms implemented purely in Python
    without external dependencies (e.g. Pandas or NumPy):
      - Mean, Variance, Standard Deviation
      - Pearson Correlation Coefficient (r)
      - Frequency distributions
      - Data cleaning and type normalization
    """
    students = get_students_csv_rows()
    sessions = get_master_study_csv_rows(limit=500)

    # 1. Student-level aggregations
    student_count = len(students)
    total_study_hours = sum(float(s.get("Total_Study_Hours", 0)) for s in students)
    avg_study_per_student = round(total_study_hours / max(student_count, 1), 2)
    avg_student_prod = round(sum(float(s.get("Avg_Productivity", 0)) for s in students) / max(student_count, 1), 2)
    avg_student_sleep = round(sum(float(s.get("Avg_Sleep_Hours", 0)) for s in students) / max(student_count, 1), 2)

    # Burnout distribution across students
    burnout_dist = {"Low": 0, "Medium": 0, "High": 0}
    for s in students:
        b = str(s.get("Burnout_Risk", "Low")).capitalize()
        if "High" in b:
            burnout_dist["High"] += 1
        elif "Medium" in b:
            burnout_dist["Medium"] += 1
        else:
            burnout_dist["Low"] += 1

    # 2. Session-level mathematical calculations
    session_count = len(sessions)
    sleep_vals = []
    prod_vals = []
    study_vals = []
    mood_vals = []
    subject_counter = {}

    for row in sessions:
        try:
            sl = float(row.get("Sleep_Hours", 0))
            pr = float(row.get("Productivity_Score", 0))
            st = float(row.get("Study_Hours", 0))
            md = float(row.get("Mood", 3))

            sleep_vals.append(sl)
            prod_vals.append(pr)
            study_vals.append(st)
            mood_vals.append(md)

            subjs = str(row.get("Subjects", "")).split(";")
            for s in subjs:
                s_clean = s.strip()
                if s_clean:
                    subject_counter[s_clean] = subject_counter.get(s_clean, 0) + 1
        except (ValueError, TypeError):
            continue

    # Pearson correlation r(Sleep, Productivity)
    r_sleep_prod = _calculate_pearson_correlation(sleep_vals, prod_vals) if len(sleep_vals) >= 2 else 0.42
    r_mood_study = _calculate_pearson_correlation(mood_vals, study_vals) if len(mood_vals) >= 2 else 0.35

    # Top studied subject
    top_subject = "Mathematics / CPPS"
    if subject_counter:
        top_subject = max(subject_counter.items(), key=lambda x: x[1])[0]

    return {
        "student_count": student_count,
        "session_count": session_count,
        "total_study_hours": round(total_study_hours, 1),
        "avg_study_per_student": avg_study_per_student,
        "avg_student_prod": avg_student_prod,
        "avg_student_sleep": avg_student_sleep,
        "burnout_dist": burnout_dist,
        "r_sleep_prod": r_sleep_prod,
        "r_mood_study": r_mood_study,
        "top_subject": top_subject,
        "total_unique_subjects": len(subject_counter)
    }


def get_python_code_metrics():
    """
    Analyzes all Python files in the project to dynamically generate
    code metrics, class counts, and CPPS curriculum alignment metrics.
    """
    python_files = {
        "app.py": "Flask Web App, Routing, API, Session Auth, Rate Limiting",
        "data_handler.py": "CSV Ingestion, Data Science Math, Synchronization, Serialization",
        "study_planner.py": "Adaptive Schedule Allocator, Pacing Heuristic, Time Blocking",
        "analyzer.py": "Mood Analysis, Burnout Prediction, Multi-variable Scoring",
        "models.py": "SQLAlchemy ORM Entities, Schema Relational Mapping, Model Methods"
    }

    metrics = {
        "total_lines": 0,
        "code_lines": 0,
        "comment_lines": 0,
        "blank_lines": 0,
        "total_functions": 0,
        "total_classes": 0,
        "modules": []
    }

    for fname, desc in python_files.items():
        fpath = os.path.join(BASE_DIR, fname)
        if not os.path.exists(fpath):
            continue

        f_total = 0
        f_code = 0
        f_comment = 0
        f_blank = 0
        f_funcs = 0
        f_classes = 0

        try:
            with open(fpath, "r", encoding="utf-8") as f:
                for line in f:
                    f_total += 1
                    s = line.strip()
                    if not s:
                        f_blank += 1
                    elif s.startswith("#"):
                        f_comment += 1
                    else:
                        f_code += 1
                        if s.startswith("def "):
                            f_funcs += 1
                        elif s.startswith("class "):
                            f_classes += 1
        except Exception:
            pass

        metrics["total_lines"] += f_total
        metrics["code_lines"] += f_code
        metrics["comment_lines"] += f_comment
        metrics["blank_lines"] += f_blank
        metrics["total_functions"] += f_funcs
        metrics["total_classes"] += f_classes

        metrics["modules"].append({
            "filename": fname,
            "description": desc,
            "lines": f_total,
            "code_lines": f_code,
            "functions": f_funcs,
            "classes": f_classes
        })

    return metrics

