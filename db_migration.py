# db_migration.py
# Migrates data from local CSV (study_data.csv) to PostgreSQL or SQLite via SQLAlchemy models.

import os
import csv
from datetime import datetime
import dotenv

# Load environment variables
dotenv.load_dotenv()

from app import app, db
from models import User, StudySession

CSV_FILE = "study_data.csv"

def run_migration():
    print("[MIGRATION] Starting database migration from CSV...")
    
    if not os.path.exists(CSV_FILE):
        print(f"[MIGRATION INFO] CSV file '{CSV_FILE}' does not exist. No historical data to migrate.")
        return True

    with app.app_context():
        # Retrieve or create a migration user
        user = User.query.first()
        if not user:
            print("[MIGRATION WARN] No users found in the database. Creating a default 'migrated_user'...")
            import bcrypt
            salt = bcrypt.gensalt()
            pw_hash = bcrypt.hashpw(b"migration_secure_pass_123", salt).decode('utf-8')
            user = User(
                username="migrated_user",
                email="migrated_user@example.com",
                password_hash=pw_hash
            )
            db.session.add(user)
            db.session.commit()
            print(f"[MIGRATION] Default user '{user.username}' created with ID {user.id}")

        # Read CSV data
        sessions = []
        try:
            with open(CSV_FILE, 'r') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    sessions.append(row)
        except Exception as e:
            print(f"[MIGRATION ERROR] Could not read CSV file: {e}")
            return False

        print(f"[MIGRATION] Found {len(sessions)} rows in CSV file.")
        if len(sessions) == 0:
            print("[MIGRATION] CSV file is empty. Nothing to import.")
            return True

        # Fetch existing sessions for this user to prevent duplicates
        existing_records = set()
        existing_sessions = StudySession.query.filter_by(user_id=user.id).all()
        for es in existing_sessions:
            date_str = es.session_date.strftime("%Y-%m-%d %H:%M:%S")
            existing_records.add((date_str, int(es.mood), float(es.study_hours), float(es.sleep_hours)))

        inserted_count = 0
        skipped_count = 0

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

                # Normalize date formatting
                parsed_date = datetime.strptime(date_val, "%Y-%m-%d %H:%M:%S")
                norm_date_str = parsed_date.strftime("%Y-%m-%d %H:%M:%S")

                # Check if this record already exists
                record_key = (norm_date_str, mood_val, study_hours_val, sleep_hours_val)
                if record_key in existing_records:
                    skipped_count += 1
                    continue

                new_session = StudySession(
                    user_id=user.id,
                    session_date=parsed_date,
                    mood=mood_val,
                    study_hours=study_hours_val,
                    sleep_hours=sleep_hours_val,
                    days_left=days_left_val,
                    subjects=subjects_val,
                    productivity_score=productivity_score_val,
                    burnout_risk=burnout_risk_val
                )
                db.session.add(new_session)
                inserted_count += 1
                # Add to set to prevent duplicating within the CSV itself
                existing_records.add(record_key)

            except Exception as e:
                print(f"[MIGRATION WARN] Failed to parse/migrate row {s}: {e}")
                continue

        if inserted_count > 0:
            db.session.commit()
        
        print(f"[MIGRATION SUCCESS] Complete! Inserted: {inserted_count}, Skipped: {skipped_count} duplicates.")
        return True

if __name__ == "__main__":
    run_migration()
