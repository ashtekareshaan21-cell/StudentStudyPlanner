# study_planner.py
# This file contains the main logic for generating study plans

from analyzer import (
    analyze_mood,
    analyze_situation,
    calculate_productivity_score,
    detect_burnout,
    allocate_study_time,
    generate_break_schedule
)


def generate_study_plan(mood_score, study_hours, days_left, subjects, sleep_hours):
    """
    Generate a complete study plan based on user input
    
    Parameters:
    - mood_score: 1-5
    - study_hours: float (hours available)
    - days_left: int (days until exam)
    - subjects: list (subjects to study)
    - sleep_hours: float (hours of sleep)
    
    Returns: dictionary with complete study plan
    """
    
    # Validate inputs
    if not subjects or len(subjects) == 0:
        subjects = ["General Study"]
    
    # Step 1: Analyze mood
    mood_analysis = analyze_mood(mood_score)
    
    # Step 2: Analyze situation
    situation_analysis = analyze_situation(days_left, study_hours)
    
    # Step 3: Calculate productivity
    productivity_score = calculate_productivity_score(mood_score, sleep_hours, study_hours)
    
    # Step 4: Detect burnout
    burnout_analysis = detect_burnout(study_hours, sleep_hours)
    
    # Step 5: Allocate study time
    # Create difficulty preference (can be customized)
    difficulty_preference = {}
    for subject in subjects:
        # Default: all subjects have equal difficulty
        difficulty_preference[subject] = 3
    
    time_allocation = allocate_study_time(subjects, study_hours, difficulty_preference)
    
    # Step 6: Generate break schedule
    breaks = generate_break_schedule(study_hours, mood_analysis['break_frequency'])
    
    # Step 7: Create study plan structure
    study_plan = {
        "mood_analysis": mood_analysis,
        "situation_analysis": situation_analysis,
        "productivity_score": productivity_score,
        "burnout_analysis": burnout_analysis,
        "time_allocation": time_allocation,
        "break_schedule": breaks,
        "total_study_hours": study_hours,
        "total_sleep_hours": sleep_hours,
        "days_until_exam": days_left,
        "subjects": subjects
    }
    
    return study_plan


def format_study_plan_for_display(study_plan):
    """
    Format study plan into a readable format
    Returns dictionary with formatted strings for display
    """
    
    formatted = {}
    
    # Mood section
    formatted['mood_level'] = study_plan['mood_analysis']['level']
    formatted['mood_recommendation'] = study_plan['mood_analysis']['recommendation']
    formatted['study_intensity'] = study_plan['mood_analysis']['study_intensity']
    
    # Situation section
    formatted['situation_status'] = study_plan['situation_analysis']['status']
    formatted['study_mode'] = study_plan['situation_analysis']['mode']
    formatted['situation_priority'] = study_plan['situation_analysis']['priority']
    formatted['hours_per_day'] = study_plan['situation_analysis']['hours_per_day']
    formatted['situation_focus'] = study_plan['situation_analysis']['focus']
    
    # Productivity section
    formatted['productivity_score'] = study_plan['productivity_score']
    
    # Burnout section
    formatted['burnout_risk'] = study_plan['burnout_analysis']['risk_level']
    formatted['burnout_warning'] = study_plan['burnout_analysis']['warning']
    formatted['burnout_advice'] = study_plan['burnout_analysis']['advice']
    
    # Time allocation section
    formatted['time_allocation'] = study_plan['time_allocation']
    
    # Breaks section
    formatted['breaks'] = study_plan['break_schedule']
    formatted['break_count'] = len(study_plan['break_schedule'])
    
    return formatted


def get_difficulty_topics(subject):
    """
    Return common difficult topics for each subject
    Can be expanded based on actual subjects
    """
    difficult_topics = {
        "Math": ["Integration", "Differential Equations", "Complex Numbers"],
        "Physics": ["Quantum Mechanics", "Relativity", "Thermodynamics"],
        "Chemistry": ["Organic Chemistry", "Equilibrium", "Kinetics"],
        "English": ["Essay Writing", "Literary Analysis", "Grammar Rules"],
        "History": ["Dates and Events", "Causes and Effects", "Timeline Analysis"],
        "Programming": ["Data Structures", "Algorithms", "Recursion"],
        "Biology": ["Genetics", "Photosynthesis", "Cellular Processes"]
    }
    
    return difficult_topics.get(subject, ["Key Concepts", "Complex Problems"])
