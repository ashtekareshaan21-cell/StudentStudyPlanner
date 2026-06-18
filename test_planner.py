# test_planner.py
# Unit tests for study planner calculations

import unittest
from study_planner import generate_study_plan, format_study_plan_for_display
from analyzer import (
    analyze_mood,
    analyze_situation,
    calculate_productivity_score,
    detect_burnout,
    allocate_study_time,
    generate_break_schedule
)

class TestStudyPlanner(unittest.TestCase):

    def test_analyze_mood(self):
        # Test low mood
        low = analyze_mood(1)
        self.assertEqual(low['study_intensity'], 'Light')
        self.assertEqual(low['break_frequency'], 5)

        # Test medium mood
        med = analyze_mood(3)
        self.assertEqual(med['study_intensity'], 'Moderate')
        self.assertEqual(med['break_frequency'], 10)

        # Test high mood
        high = analyze_mood(5)
        self.assertEqual(high['study_intensity'], 'Deep')
        self.assertEqual(high['break_frequency'], 15)

    def test_analyze_situation(self):
        # Urgent exam case
        urgent = analyze_situation(days_left=2, available_hours=8)
        self.assertEqual(urgent['status'], 'URGENT')
        self.assertEqual(urgent['mode'], 'Revision Mode')
        
        # Comfortable case
        comf = analyze_situation(days_left=10, available_hours=10)
        self.assertEqual(comf['status'], 'COMFORTABLE')

    def test_calculate_productivity_score(self):
        # Perfect conditions: High mood (5), 8h sleep, 8h study
        score = calculate_productivity_score(mood_score=5, sleep_hours=8, study_hours=8)
        self.assertEqual(score, 100)

        # Deprived conditions: Low mood (1), 4h sleep, 2h study
        score_low = calculate_productivity_score(mood_score=1, sleep_hours=4, study_hours=2)
        # Mood: (1/5)*25 = 5. Sleep: 10 points. Study: (2/8)*50 = 12.5. Total = 27.5
        self.assertEqual(score_low, 27.5)

    def test_detect_burnout(self):
        # Very High risk: study hours between 5-6 and sleep below 5
        burnout = detect_burnout(study_hours=5.5, sleep_hours=4.5)
        self.assertEqual(burnout['risk_level'], 'Very High')
        self.assertTrue(burnout['warning'])

        # High risk: study hours >= 6 and sleep below 6
        burnout_high = detect_burnout(study_hours=8, sleep_hours=5)
        self.assertEqual(burnout_high['risk_level'], 'High')
        self.assertTrue(burnout_high['warning'])

        # Balanced study and sleep
        healthy = detect_burnout(study_hours=4, sleep_hours=8)
        self.assertEqual(healthy['risk_level'], 'Low')
        self.assertFalse(healthy['warning'])

    def test_allocate_study_time(self):
        subjects = ['Math', 'Physics', 'History']
        difficulty = {'Math': 4, 'Physics': 5, 'History': 3}
        
        # Total difficulty = 12. Available hours = 6.
        # Math gets (4/12)*6 = 2. Physics gets (5/12)*6 = 2.5. History gets (3/12)*6 = 1.5.
        allocation = allocate_study_time(subjects, available_hours=6, difficulty_preference=difficulty)
        self.assertEqual(allocation['Math'], 2.0)
        self.assertEqual(allocation['Physics'], 2.5)
        self.assertEqual(allocation['History'], 1.5)

    def test_generate_break_schedule(self):
        # Study hours = 2 (120 min), break frequency = 30
        # Breaks at 30, 60, 90, 120
        breaks = generate_break_schedule(study_hours=2.0, break_frequency=30)
        self.assertEqual(len(breaks), 4)
        self.assertEqual(breaks[0], '0h 30m')
        self.assertEqual(breaks[1], '1h 0m')

    def test_generate_study_plan_flow(self):
        subjects = ['Math', 'Physics']
        plan = generate_study_plan(mood_score=4, study_hours=4.0, days_left=5, subjects=subjects, sleep_hours=7.0)
        
        self.assertIn('productivity_score', plan)
        self.assertIn('burnout_analysis', plan)
        self.assertIn('time_allocation', plan)
        self.assertEqual(plan['total_study_hours'], 4.0)

if __name__ == '__main__':
    unittest.main()
