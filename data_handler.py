# data_handler.py
# This file handles database and CSV operations for storing and retrieving study history

import csv
import os
from datetime import datetime
import mysql.connector

CSV_FILE = "study_data.csv"

# MySQL Configuration from Environment Variables
DB_HOST = os.getenv("MYSQL_HOST")
DB_USER = os.getenv("MYSQL_USER")
DB_PASSWORD = os.getenv("MYSQL_PASSWORD")
DB_DATABASE = os.getenv("MYSQL_DATABASE")
DB_PORT = os.getenv("MYSQL_PORT", "3306")

def get_db_connection():
    """
    Attempts to establish a connection to the MySQL database.
    Returns the connection object if successful, otherwise None.
    """
    if not DB_HOST or not DB_USER or not DB_DATABASE:
        # DB details not fully configured, silently use CSV fallback
        return None
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_DATABASE,
            port=int(DB_PORT),
            connect_timeout=3
        )
        return conn
    except Exception as e:
        print(f"[WARN] Failed to connect to MySQL database: {e}. Falling back to CSV.")
        return None

def initialize_db():
    """
    Creates the study_sessions table in the database if it doesn't exist.
    """
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS study_sessions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    session_date DATETIME NOT NULL,
                    mood INT NOT NULL,
                    study_hours FLOAT NOT NULL,
                    sleep_hours FLOAT NOT NULL,
                    days_left INT NOT NULL,
                    subjects TEXT NOT NULL,
                    productivity_score FLOAT NOT NULL,
                    burnout_risk VARCHAR(50) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"[ERROR] Database table initialization failed: {e}")
            if conn.is_connected():
                conn.close()
    return False

def initialize_csv():
    """
    Create CSV file with headers if it doesn't exist
    """
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([
                "Date",
                "Mood",
                "Study_Hours",
                "Sleep_Hours",
                "Days_Left",
                "Subjects",
                "Productivity_Score",
                "Burnout_Risk"
            ])

def save_study_session(mood, study_hours, sleep_hours, days_left, subjects, productivity_score, burnout_risk):
    """
    Save a study session to MySQL or CSV (as fallback)
    """
    # 1. Try MySQL database write
    conn = get_db_connection()
    if conn:
        try:
            # Ensure tables are initialized
            initialize_db()
            cursor = conn.cursor()
            query = """
                INSERT INTO study_sessions (session_date, mood, study_hours, sleep_hours, days_left, subjects, productivity_score, burnout_risk)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            session_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(query, (
                session_date,
                int(mood),
                float(study_hours),
                float(sleep_hours),
                int(days_left),
                ";".join(subjects),
                float(productivity_score),
                str(burnout_risk)
            ))
            conn.commit()
            cursor.close()
            conn.close()
            print("[INFO] Saved session to MySQL database successfully.")
            return
        except Exception as e:
            print(f"[ERROR] Failed to save session to MySQL: {e}. Trying CSV fallback.")
            if conn.is_connected():
                conn.close()

    # 2. Fallback: Save to CSV
    initialize_csv()
    with open(CSV_FILE, 'a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            mood,
            study_hours,
            sleep_hours,
            days_left,
            ";".join(subjects),
            productivity_score,
            burnout_risk
        ])
    print("[INFO] Saved session to CSV file.")

def get_all_sessions():
    """
    Read all study sessions from MySQL or CSV (as fallback)
    Returns list of dictionaries
    """
    # 1. Try MySQL database read
    conn = get_db_connection()
    if conn:
        try:
            # Ensure tables are initialized
            initialize_db()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT 
                    session_date as Date, 
                    mood as Mood, 
                    study_hours as Study_Hours, 
                    sleep_hours as Sleep_Hours, 
                    days_left as Days_Left, 
                    subjects as Subjects, 
                    productivity_score as Productivity_Score, 
                    burnout_risk as Burnout_Risk 
                FROM study_sessions 
                ORDER BY id ASC
            """)
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            # Format results to match CSV DictReader string output format
            sessions = []
            for row in rows:
                if isinstance(row['Date'], datetime):
                    row['Date'] = row['Date'].strftime("%Y-%m-%d %H:%M:%S")
                # Convert all values to string to keep identical behavior with CSV reader
                sessions.append({
                    "Date": str(row['Date']),
                    "Mood": str(row['Mood']),
                    "Study_Hours": str(row['Study_Hours']),
                    "Sleep_Hours": str(row['Sleep_Hours']),
                    "Days_Left": str(row['Days_Left']),
                    "Subjects": str(row['Subjects']),
                    "Productivity_Score": str(row['Productivity_Score']),
                    "Burnout_Risk": str(row['Burnout_Risk'])
                })
            return sessions
        except Exception as e:
            print(f"[ERROR] Failed to fetch sessions from MySQL: {e}. Trying CSV fallback.")
            if conn.is_connected():
                conn.close()

    # 2. Fallback: Read from CSV
    initialize_csv()
    sessions = []
    with open(CSV_FILE, 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            sessions.append(row)
    return sessions

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

