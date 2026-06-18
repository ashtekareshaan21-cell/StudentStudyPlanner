# db_migration.py
# Migrates data from local CSV (study_data.csv) to the MySQL database.

import os
import csv
import mysql.connector
from datetime import datetime
import dotenv

# Load environment variables
dotenv.load_dotenv()

DB_HOST = os.getenv("MYSQL_HOST")
DB_USER = os.getenv("MYSQL_USER")
DB_PASSWORD = os.getenv("MYSQL_PASSWORD")
DB_DATABASE = os.getenv("MYSQL_DATABASE")
DB_PORT = os.getenv("MYSQL_PORT", "3306")
CSV_FILE = "study_data.csv"

def run_migration():
    print("[MIGRATION] Starting database migration...")
    
    if not DB_HOST or not DB_USER or not DB_DATABASE:
        print("[MIGRATION ERROR] Database environment variables are not fully configured.")
        print("[MIGRATION ERROR] Please check MYSQL_HOST, MYSQL_USER, and MYSQL_DATABASE.")
        return False
        
    if not os.path.exists(CSV_FILE):
        print(f"[MIGRATION INFO] CSV file '{CSV_FILE}' does not exist. No historical data to migrate.")
        # Create empty table anyway
        create_empty_table()
        return True

    # Connect to MySQL
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_DATABASE,
            port=int(DB_PORT)
        )
    except Exception as e:
        print(f"[MIGRATION ERROR] Could not connect to MySQL database: {e}")
        return False

    try:
        cursor = conn.cursor()
        
        # Create table if it doesn't exist
        print("[MIGRATION] Ensuring study_sessions table exists...")
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

        # Count existing rows to check if already migrated
        cursor.execute("SELECT COUNT(*) FROM study_sessions")
        db_count = cursor.fetchone()[0]
        print(f"[MIGRATION] Current database rows: {db_count}")

        # Read CSV data
        sessions = []
        with open(CSV_FILE, 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                sessions.append(row)
        
        print(f"[MIGRATION] Found {len(sessions)} rows in CSV file.")

        if len(sessions) == 0:
            print("[MIGRATION] CSV file is empty. Nothing to import.")
            cursor.close()
            conn.close()
            return True

        inserted_count = 0
        skipped_count = 0

        # Query existing sessions from DB to prevent duplicate migration
        cursor.execute("SELECT session_date, mood, study_hours, sleep_hours FROM study_sessions")
        existing_records = set()
        for r in cursor.fetchall():
            # Format datetime as string to match CSV representation
            date_str = r[0].strftime("%Y-%m-%d %H:%M:%S") if isinstance(r[0], datetime) else str(r[0])
            # key: (date, mood, study_hours, sleep_hours)
            existing_records.add((date_str, int(r[1]), float(r[2]), float(r[3])))

        # Insert CSV rows
        insert_query = """
            INSERT INTO study_sessions (session_date, mood, study_hours, sleep_hours, days_left, subjects, productivity_score, burnout_risk)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        for s in sessions:
            try:
                date_val = s['Date']
                mood_val = int(s['Mood'])
                study_hours_val = float(s['Study_Hours'])
                sleep_hours_val = float(s['Sleep_Hours'])
                days_left_val = int(s['Days_Left'])
                subjects_val = s['Subjects']
                productivity_score_val = float(s['Productivity_Score'])
                burnout_risk_val = s['Burnout_Risk']

                # Check if this record already exists in DB
                record_key = (date_val, mood_val, study_hours_val, sleep_hours_val)
                if record_key in existing_records:
                    skipped_count += 1
                    continue

                cursor.execute(insert_query, (
                    date_val,
                    mood_val,
                    study_hours_val,
                    sleep_hours_val,
                    days_left_val,
                    subjects_val,
                    productivity_score_val,
                    burnout_risk_val
                ))
                inserted_count += 1
            except Exception as e:
                print(f"[MIGRATION WARN] Failed to parse/migrate row {s}: {e}")
                continue

        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"[MIGRATION SUCCESS] Complete! Inserted: {inserted_count}, Skipped: {skipped_count} duplicates.")
        return True

    except Exception as e:
        print(f"[MIGRATION ERROR] Migration failed: {e}")
        if conn.is_connected():
            conn.close()
        return False

def create_empty_table():
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_DATABASE,
            port=int(DB_PORT)
        )
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
        print("[MIGRATION] Created empty study_sessions table in database.")
    except Exception as e:
        print(f"[MIGRATION ERROR] Could not create empty table: {e}")

if __name__ == "__main__":
    run_migration()
