# analyzer.py
# This file contains all logic for analyzing study mood, situations, and productivity

def analyze_mood(mood_score):
    """
    Analyze mood and return study recommendation
    mood_score: 1-5 (1=very bad, 5=excellent)
    """
    if mood_score <= 2:
        return {
            "level": "Low",
            "recommendation": "Light study with frequent breaks",
            "study_intensity": "Light",
            "break_frequency": 5  # break every 5 minutes
        }
    elif mood_score == 3:
        return {
            "level": "Medium",
            "recommendation": "Moderate study with regular breaks",
            "study_intensity": "Moderate",
            "break_frequency": 10  # break every 10 minutes
        }
    else:  # mood_score >= 4
        return {
            "level": "High",
            "recommendation": "Deep study sessions possible",
            "study_intensity": "Deep",
            "break_frequency": 15  # break every 15 minutes
        }


def analyze_situation(days_left, available_hours):
    """
    Analyze the exam situation based on days left and available hours
    """
    hours_per_day = available_hours / (days_left + 1)  # +1 to avoid division by zero
    
    if days_left <= 3:
        return {
            "status": "URGENT",
            "mode": "Revision Mode",
            "priority": "Critical",
            "hours_per_day": round(hours_per_day, 2),
            "focus": "Focus on past papers and key topics"
        }
    elif days_left <= 7:
        return {
            "status": "NEAR",
            "mode": "Intensive Study",
            "priority": "High",
            "hours_per_day": round(hours_per_day, 2),
            "focus": "Complete remaining topics and practice"
        }
    else:
        return {
            "status": "COMFORTABLE",
            "mode": "Regular Study",
            "priority": "Medium",
            "hours_per_day": round(hours_per_day, 2),
            "focus": "Systematic learning with depth"
        }


def calculate_productivity_score(mood_score, sleep_hours, study_hours):
    """
    Calculate productivity score based on mood, sleep, and study hours
    Score: 0-100
    """
    # Mood contribution (25%)
    mood_points = (mood_score / 5) * 25
    
    # Sleep contribution (25%) - ideal is 7-8 hours
    if 6 <= sleep_hours <= 8:
        sleep_points = 25
    elif 5 <= sleep_hours < 6 or 8 < sleep_hours <= 9:
        sleep_points = 20
    elif sleep_hours < 5 or sleep_hours > 9:
        sleep_points = 10
    else:
        sleep_points = 15
    
    # Study hours contribution (50%) - more hours = more productivity
    study_points = min((study_hours / 8) * 50, 50)  # Cap at 50, assuming 8 hours is max productive
    
    total_score = mood_points + sleep_points + study_points
    return round(total_score, 2)


def detect_burnout(study_hours, sleep_hours, days_count=1):
    """
    Detect if user is at risk of burnout
    Returns warning level and advice
    """
    burnout_risk = "Low"
    advice = "Keep up the good balance!"
    warning = False
    
    # Check if study hours are too high and sleep too low
    if study_hours >= 6 and sleep_hours < 6:
        burnout_risk = "High"
        advice = "⚠️ WARNING: Too much study with low sleep! Risk of burnout. Please get more rest."
        warning = True
    elif study_hours >= 5 and sleep_hours < 5:
        burnout_risk = "Very High"
        advice = "🚨 CRITICAL: Severe burnout risk! Reduce study hours and increase sleep immediately."
        warning = True
    elif study_hours >= 6 and sleep_hours < 7:
        burnout_risk = "Medium"
        advice = "⚠️ CAUTION: Moderately high burnout risk. Try to get at least 7 hours of sleep."
        warning = True
    
    return {
        "risk_level": burnout_risk,
        "warning": warning,
        "advice": advice
    }


def allocate_study_time(subjects_list, available_hours, difficulty_preference=None):
    """
    Allocate study time between subjects
    subjects_list: list of subject names
    available_hours: total hours available
    difficulty_preference: dictionary with subject: difficulty (1-5, 5=hardest)
    
    Returns dictionary with subject: hours allocation
    """
    if not subjects_list:
        return {}
    
    # If no difficulty specified, allocate equally
    if difficulty_preference is None:
        difficulty_preference = {subject: 3 for subject in subjects_list}
    
    # Calculate total difficulty
    total_difficulty = sum(difficulty_preference.get(subject, 3) for subject in subjects_list)
    
    # Allocate time proportional to difficulty
    allocation = {}
    for subject in subjects_list:
        difficulty = difficulty_preference.get(subject, 3)
        allocated_time = (difficulty / total_difficulty) * available_hours
        allocation[subject] = round(allocated_time, 2)
    
    return allocation


def generate_break_schedule(study_hours, break_frequency):
    """
    Generate break schedule during study session
    study_hours: total study hours
    break_frequency: how many minutes between breaks
    
    Returns list of break times
    """
    total_minutes = int(study_hours * 60)
    breaks = []
    current_time = 0
    
    while current_time + break_frequency <= total_minutes:
        current_time += break_frequency
        minutes = current_time % 60
        hours = current_time // 60
        breaks.append(f"{hours}h {minutes}m")
    
    return breaks
