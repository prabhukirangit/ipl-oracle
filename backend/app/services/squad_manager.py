"""
SquadManager — Team squad management and injury tracking.

Maintains the current squad state for both teams in a match.
Tracks: availability, injuries, last-match XI, probable XI.

SQUAD_SEED contains all 10 IPL 2026 teams with birth_year and ipl_debut_year
for age/experience steering factors (computed in AgentFactory).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Availability status constants
STATUS_CONFIRMED = "confirmed"
STATUS_DOUBTFUL = "doubtful"
STATUS_RULED_OUT = "ruled_out"

VALID_STATUSES = {STATUS_CONFIRMED, STATUS_DOUBTFUL, STATUS_RULED_OUT}

# IPL 2026 squad seed data — key players per team (post Dec 2025 mini-auction)
# Used as fallback when live data is unavailable
# Source: espncricinfo.com, iplt20.com, crictracker.com — March 2026
SQUAD_SEED: dict[str, list[dict[str, Any]]] = {
    "Mumbai Indians": [
        {"name": "Hardik Pandya", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1993, "ipl_debut_year": 2015},
        {"name": "Rohit Sharma", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 1987, "ipl_debut_year": 2008},
        {"name": "Suryakumar Yadav", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 1990, "ipl_debut_year": 2012},
        {"name": "Jasprit Bumrah", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1993, "ipl_debut_year": 2013},
        {"name": "Tilak Varma", "role": "batsman", "batting_style": "left_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 2002, "ipl_debut_year": 2022},
        {"name": "Trent Boult", "role": "bowler", "batting_style": "right_hand", "bowling_style": "left_arm_pace", "is_foreign": True, "birth_year": 1989, "ipl_debut_year": 2017},
        {"name": "Quinton de Kock", "role": "wicketkeeper", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1992, "ipl_debut_year": 2012},
        {"name": "Will Jacks", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1998, "ipl_debut_year": 2024},
        {"name": "Deepak Chahar", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1992, "ipl_debut_year": 2014},
        {"name": "Mitchell Santner", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": True, "birth_year": 1992, "ipl_debut_year": 2018},
        {"name": "Naman Dhir", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 2003, "ipl_debut_year": 2024},
        {"name": "Sherfane Rutherford", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1998, "ipl_debut_year": 2019},
        {"name": "Ryan Rickelton", "role": "batsman", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1996, "ipl_debut_year": 2025},
        {"name": "Robin Minz", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2003, "ipl_debut_year": 2025},
        {"name": "Shardul Thakur", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1991, "ipl_debut_year": 2015},
        {"name": "Corbin Bosch", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1998, "ipl_debut_year": 2025},
        {"name": "Allah Ghazanfar", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 2005, "ipl_debut_year": 2025},
        {"name": "Raj Angad Bawa", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 2002, "ipl_debut_year": 2022},
    ],
    "Chennai Super Kings": [
        {"name": "Ruturaj Gaikwad", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 1997, "ipl_debut_year": 2019},
        {"name": "Sanju Samson", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1994, "ipl_debut_year": 2013},
        {"name": "MS Dhoni", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1981, "ipl_debut_year": 2008},
        {"name": "Shivam Dube", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1993, "ipl_debut_year": 2019},
        {"name": "Sarfaraz Khan", "role": "batsman", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": False, "birth_year": 1997, "ipl_debut_year": 2015},
        {"name": "Khaleel Ahmed", "role": "bowler", "batting_style": "right_hand", "bowling_style": "left_arm_pace", "is_foreign": False, "birth_year": 1998, "ipl_debut_year": 2018},
        {"name": "Rahul Chahar", "role": "bowler", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": False, "birth_year": 1999, "ipl_debut_year": 2018},
        {"name": "Noor Ahmad", "role": "bowler", "batting_style": "right_hand", "bowling_style": "left_arm_spin", "is_foreign": True, "birth_year": 2005, "ipl_debut_year": 2024},
        {"name": "Nathan Ellis", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1994, "ipl_debut_year": 2022},
        {"name": "Dewald Brevis", "role": "batsman", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": True, "birth_year": 2003, "ipl_debut_year": 2022},
        {"name": "Jamie Overton", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1994, "ipl_debut_year": 2025},
        {"name": "Matthew Short", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1997, "ipl_debut_year": 2026},
        {"name": "Mukesh Choudhary", "role": "bowler", "batting_style": "right_hand", "bowling_style": "left_arm_pace", "is_foreign": False, "birth_year": 1997, "ipl_debut_year": 2022},
        {"name": "Shreyas Gopal", "role": "bowler", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": False, "birth_year": 1993, "ipl_debut_year": 2014},
        {"name": "Ayush Mhatre", "role": "batsman", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2007, "ipl_debut_year": 2025},
        {"name": "Matt Henry", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1991, "ipl_debut_year": 2023},
    ],
    "Royal Challengers Bengaluru": [
        {"name": "Rajat Patidar", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 1993, "ipl_debut_year": 2021},
        {"name": "Virat Kohli", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 1988, "ipl_debut_year": 2008},
        {"name": "Phil Salt", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1996, "ipl_debut_year": 2023},
        {"name": "Jacob Bethell", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": True, "birth_year": 2003, "ipl_debut_year": 2025},
        {"name": "Tim David", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1996, "ipl_debut_year": 2022},
        {"name": "Krunal Pandya", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 1991, "ipl_debut_year": 2016},
        {"name": "Josh Hazlewood", "role": "bowler", "batting_style": "left_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1991, "ipl_debut_year": 2020},
        {"name": "Nuwan Thushara", "role": "bowler", "batting_style": "right_hand", "bowling_style": "left_arm_pace", "is_foreign": True, "birth_year": 1995, "ipl_debut_year": 2024},
        {"name": "Rasikh Dar", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 2001, "ipl_debut_year": 2019},
        {"name": "Bhuvneshwar Kumar", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1990, "ipl_debut_year": 2011},
        {"name": "Romario Shepherd", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1994, "ipl_debut_year": 2022},
        {"name": "Devdutt Padikkal", "role": "batsman", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2000, "ipl_debut_year": 2020},
        {"name": "Jitesh Sharma", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1994, "ipl_debut_year": 2022},
        {"name": "Venkatesh Iyer", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1994, "ipl_debut_year": 2021},
        {"name": "Suyash Sharma", "role": "bowler", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": False, "birth_year": 2003, "ipl_debut_year": 2023},
        {"name": "Swapnil Singh", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 1993, "ipl_debut_year": 2022},
    ],
    "Kolkata Knight Riders": [
        {"name": "Ajinkya Rahane", "role": "batsman", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1988, "ipl_debut_year": 2008},
        {"name": "Rinku Singh", "role": "batsman", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1997, "ipl_debut_year": 2018},
        {"name": "Sunil Narine", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1988, "ipl_debut_year": 2012},
        {"name": "Varun Chakravarthy", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 1991, "ipl_debut_year": 2019},
        {"name": "Harshit Rana", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 2002, "ipl_debut_year": 2024},
        {"name": "Cameron Green", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1999, "ipl_debut_year": 2023},
        {"name": "Matheesha Pathirana", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 2002, "ipl_debut_year": 2023},
        {"name": "Rachin Ravindra", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": True, "birth_year": 1999, "ipl_debut_year": 2024},
        {"name": "Finn Allen", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1999, "ipl_debut_year": 2022},
        {"name": "Angkrish Raghuvanshi", "role": "batsman", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2004, "ipl_debut_year": 2023},
        {"name": "Ramandeep Singh", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1997, "ipl_debut_year": 2022},
        {"name": "Manish Pandey", "role": "batsman", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1989, "ipl_debut_year": 2008},
        {"name": "Rovman Powell", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1993, "ipl_debut_year": 2022},
        {"name": "Rahul Tripathi", "role": "batsman", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": False, "birth_year": 1990, "ipl_debut_year": 2017},
        {"name": "Vaibhav Arora", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1998, "ipl_debut_year": 2022},
        {"name": "Umran Malik", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 2000, "ipl_debut_year": 2021},
        {"name": "Blessing Muzarabani", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1996, "ipl_debut_year": 2026},
    ],
    "Delhi Capitals": [
        {"name": "Axar Patel", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 1994, "ipl_debut_year": 2014},
        {"name": "KL Rahul", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1992, "ipl_debut_year": 2013},
        {"name": "Mitchell Starc", "role": "bowler", "batting_style": "left_hand", "bowling_style": "left_arm_pace", "is_foreign": True, "birth_year": 1990, "ipl_debut_year": 2015},
        {"name": "Kuldeep Yadav", "role": "bowler", "batting_style": "left_hand", "bowling_style": "legbreak", "is_foreign": False, "birth_year": 1994, "ipl_debut_year": 2012},
        {"name": "Karun Nair", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 1991, "ipl_debut_year": 2013},
        {"name": "Tristan Stubbs", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 2001, "ipl_debut_year": 2023},
        {"name": "David Miller", "role": "batsman", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1989, "ipl_debut_year": 2012},
        {"name": "T Natarajan", "role": "bowler", "batting_style": "right_hand", "bowling_style": "left_arm_pace", "is_foreign": False, "birth_year": 1991, "ipl_debut_year": 2017},
        {"name": "Abishek Porel", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2001, "ipl_debut_year": 2023},
        {"name": "Lungi Ngidi", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1996, "ipl_debut_year": 2018},
        {"name": "Ben Duckett", "role": "batsman", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1994, "ipl_debut_year": 2026},
        {"name": "Pathum Nissanka", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1998, "ipl_debut_year": 2026},
        {"name": "Sameer Rizvi", "role": "batsman", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2003, "ipl_debut_year": 2024},
        {"name": "Dushmantha Chameera", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1992, "ipl_debut_year": 2021},
        {"name": "Kyle Jamieson", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1994, "ipl_debut_year": 2021},
    ],
    "Sunrisers Hyderabad": [
        {"name": "Pat Cummins", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1993, "ipl_debut_year": 2014},
        {"name": "Ishan Kishan", "role": "wicketkeeper", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1998, "ipl_debut_year": 2018},
        {"name": "Travis Head", "role": "batsman", "batting_style": "left_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1993, "ipl_debut_year": 2020},
        {"name": "Heinrich Klaasen", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1991, "ipl_debut_year": 2023},
        {"name": "Abhishek Sharma", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 2000, "ipl_debut_year": 2020},
        {"name": "Nitish Kumar Reddy", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 2003, "ipl_debut_year": 2024},
        {"name": "Harshal Patel", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1990, "ipl_debut_year": 2012},
        {"name": "Brydon Carse", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1995, "ipl_debut_year": 2025},
        {"name": "Kamindu Mendis", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1998, "ipl_debut_year": 2025},
        {"name": "Liam Livingstone", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": True, "birth_year": 1993, "ipl_debut_year": 2019},
        {"name": "Jaydev Unadkat", "role": "bowler", "batting_style": "left_hand", "bowling_style": "left_arm_pace", "is_foreign": False, "birth_year": 1991, "ipl_debut_year": 2010},
        {"name": "Shivam Mavi", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 2000, "ipl_debut_year": 2018},
        {"name": "Zeeshan Ansari", "role": "bowler", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 2003, "ipl_debut_year": 2024},
        {"name": "Jack Edwards", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1997, "ipl_debut_year": 2026},
    ],
    "Rajasthan Royals": [
        {"name": "Riyan Parag", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 2001, "ipl_debut_year": 2019},
        {"name": "Yashasvi Jaiswal", "role": "batsman", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 2001, "ipl_debut_year": 2020},
        {"name": "Shimron Hetmyer", "role": "batsman", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1996, "ipl_debut_year": 2019},
        {"name": "Dhruv Jurel", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2002, "ipl_debut_year": 2023},
        {"name": "Ravindra Jadeja", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 1988, "ipl_debut_year": 2008},
        {"name": "Sam Curran", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_pace", "is_foreign": True, "birth_year": 1998, "ipl_debut_year": 2019},
        {"name": "Jofra Archer", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1995, "ipl_debut_year": 2018},
        {"name": "Ravi Bishnoi", "role": "bowler", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": False, "birth_year": 2000, "ipl_debut_year": 2020},
        {"name": "Tushar Deshpande", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1994, "ipl_debut_year": 2020},
        {"name": "Vaibhav Suryavanshi", "role": "batsman", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2010, "ipl_debut_year": 2025},
        {"name": "Lhuan-dre Pretorius", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_pace", "is_foreign": True, "birth_year": 2001, "ipl_debut_year": 2025},
        {"name": "Kwena Maphaka", "role": "bowler", "batting_style": "left_hand", "bowling_style": "left_arm_pace", "is_foreign": True, "birth_year": 2007, "ipl_debut_year": 2025},
        {"name": "Donovan Ferreira", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1999, "ipl_debut_year": 2025},
        {"name": "Nandre Burger", "role": "bowler", "batting_style": "right_hand", "bowling_style": "left_arm_pace", "is_foreign": True, "birth_year": 1998, "ipl_debut_year": 2025},
        {"name": "Shubham Dubey", "role": "batsman", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2001, "ipl_debut_year": 2024},
    ],
    "Punjab Kings": [
        {"name": "Shreyas Iyer", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 1994, "ipl_debut_year": 2015},
        {"name": "Marcus Stoinis", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1989, "ipl_debut_year": 2016},
        {"name": "Arshdeep Singh", "role": "bowler", "batting_style": "left_hand", "bowling_style": "left_arm_pace", "is_foreign": False, "birth_year": 1999, "ipl_debut_year": 2019},
        {"name": "Marco Jansen", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_pace", "is_foreign": True, "birth_year": 1999, "ipl_debut_year": 2022},
        {"name": "Lockie Ferguson", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1991, "ipl_debut_year": 2019},
        {"name": "Yuzvendra Chahal", "role": "bowler", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": False, "birth_year": 1990, "ipl_debut_year": 2011},
        {"name": "Azmatullah Omarzai", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1999, "ipl_debut_year": 2024},
        {"name": "Prabhsimran Singh", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2000, "ipl_debut_year": 2019},
        {"name": "Shashank Singh", "role": "batsman", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1993, "ipl_debut_year": 2022},
        {"name": "Harpreet Brar", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 1995, "ipl_debut_year": 2021},
        {"name": "Nehal Wadhera", "role": "batsman", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2002, "ipl_debut_year": 2024},
        {"name": "Xavier Bartlett", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1998, "ipl_debut_year": 2025},
        {"name": "Cooper Connolly", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": True, "birth_year": 2003, "ipl_debut_year": 2026},
        {"name": "Vijaykumar Vyshak", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1998, "ipl_debut_year": 2024},
        {"name": "Musheer Khan", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 2004, "ipl_debut_year": 2025},
    ],
    "Gujarat Titans": [
        {"name": "Shubman Gill", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 1999, "ipl_debut_year": 2019},
        {"name": "Sai Sudharsan", "role": "batsman", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 2001, "ipl_debut_year": 2022},
        {"name": "Rashid Khan", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": True, "birth_year": 1998, "ipl_debut_year": 2017},
        {"name": "Mohammed Siraj", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1994, "ipl_debut_year": 2017},
        {"name": "Jos Buttler", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1990, "ipl_debut_year": 2016},
        {"name": "Washington Sundar", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 1999, "ipl_debut_year": 2017},
        {"name": "Glenn Phillips", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1996, "ipl_debut_year": 2024},
        {"name": "Jason Holder", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1991, "ipl_debut_year": 2016},
        {"name": "Prasidh Krishna", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1996, "ipl_debut_year": 2018},
        {"name": "Shahrukh Khan", "role": "batsman", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1995, "ipl_debut_year": 2021},
        {"name": "Rahul Tewatia", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": False, "birth_year": 1993, "ipl_debut_year": 2014},
        {"name": "Ishant Sharma", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1988, "ipl_debut_year": 2008},
        {"name": "Manav Suthar", "role": "bowler", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 2002, "ipl_debut_year": 2024},
        {"name": "Kumar Kushagra", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2001, "ipl_debut_year": 2023},
        {"name": "Tom Banton", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1998, "ipl_debut_year": 2026},
    ],
    "Lucknow Super Giants": [
        {"name": "Rishabh Pant", "role": "wicketkeeper", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1997, "ipl_debut_year": 2016},
        {"name": "Nicholas Pooran", "role": "wicketkeeper", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1995, "ipl_debut_year": 2019},
        {"name": "Mitchell Marsh", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1991, "ipl_debut_year": 2015},
        {"name": "Aiden Markram", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1994, "ipl_debut_year": 2022},
        {"name": "Mayank Yadav", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 2002, "ipl_debut_year": 2024},
        {"name": "Avesh Khan", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1996, "ipl_debut_year": 2017},
        {"name": "Mohsin Khan", "role": "bowler", "batting_style": "right_hand", "bowling_style": "left_arm_pace", "is_foreign": False, "birth_year": 1998, "ipl_debut_year": 2022},
        {"name": "Wanindu Hasaranga", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": True, "birth_year": 1997, "ipl_debut_year": 2022},
        {"name": "Ayush Badoni", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 2000, "ipl_debut_year": 2022},
        {"name": "Mohammed Shami", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1990, "ipl_debut_year": 2015},
        {"name": "Shahbaz Ahmed", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 1994, "ipl_debut_year": 2020},
        {"name": "Anrich Nortje", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1993, "ipl_debut_year": 2020},
        {"name": "Abdul Samad", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 2001, "ipl_debut_year": 2020},
        {"name": "Josh Inglis", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1995, "ipl_debut_year": 2025},
        {"name": "Arshin Kulkarni", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 2003, "ipl_debut_year": 2025},
    ],
}


class SquadManager:
    """
    Manages squad state for a single team in a match.

    Tracks availability, injuries, and probable XI composition.
    """

    def __init__(self, team_name: str) -> None:
        self._team = team_name
        # player_name → availability status
        self._availability: dict[str, str] = {}
        # Full squad list (from seed or live fetch)
        self._squad: list[dict[str, Any]] = []
        # Confirmed playing XI (set when available)
        self._playing_xi: list[str] = []
        # Impact Player pool (5 named subs)
        self._impact_pool: list[str] = []
        # Injury log: list of {player, description, reported_at}
        self._injury_log: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Squad loading
    # ------------------------------------------------------------------

    def load_seed_squad(self) -> None:
        """Load squad from built-in seed data."""
        squad_data = SQUAD_SEED.get(self._team, [])
        self._squad = list(squad_data)
        for player in self._squad:
            self._availability[player["name"]] = STATUS_CONFIRMED
        logger.info("SquadManager: loaded %d players for %s", len(self._squad), self._team)

    def load_squad(self, players: list[dict[str, Any]]) -> None:
        """
        Load squad from external source (live fetch or scraped data).

        Args:
            players: List of player dicts, each with at minimum 'name' key.
        """
        self._squad = list(players)
        for player in self._squad:
            name = player.get("name", "")
            if name and name not in self._availability:
                self._availability[name] = STATUS_CONFIRMED
        logger.info("SquadManager: loaded %d players for %s", len(self._squad), self._team)

    # ------------------------------------------------------------------
    # Availability management
    # ------------------------------------------------------------------

    def update_availability(self, player_name: str, status: str) -> None:
        """
        Update a player's availability status.

        Args:
            player_name: Player name
            status: 'confirmed' | 'doubtful' | 'ruled_out'
        """
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid availability status: {status!r}. Must be one of {VALID_STATUSES}")
        old_status = self._availability.get(player_name, "unknown")
        self._availability[player_name] = status
        if old_status != status:
            logger.info("SquadManager: %s → %s for %s", old_status, status, player_name)

    def get_availability(self, player_name: str) -> str:
        """Return availability status for a player."""
        return self._availability.get(player_name, STATUS_CONFIRMED)

    def mark_injury(
        self, player_name: str, description: str, severity: str = "doubtful"
    ) -> None:
        """
        Record an injury and update player availability.

        Args:
            player_name: Player name
            description: Injury description (e.g. "hamstring strain")
            severity: 'doubtful' | 'ruled_out'
        """
        import datetime
        self._injury_log.append({
            "player": player_name,
            "description": description,
            "severity": severity,
            "reported_at": datetime.datetime.utcnow().isoformat(),
        })
        self.update_availability(player_name, severity)

    # ------------------------------------------------------------------
    # Playing XI
    # ------------------------------------------------------------------

    def set_playing_xi(self, xi: list[str]) -> None:
        """Set confirmed playing XI (11 names)."""
        if len(xi) != 11:
            raise ValueError(f"Playing XI must have exactly 11 players, got {len(xi)}")
        self._playing_xi = list(xi)

    def get_playing_xi(self) -> list[str]:
        """Return confirmed playing XI, or empty list if not set."""
        return list(self._playing_xi)

    def set_impact_pool(self, pool: list[str]) -> None:
        """Set the 5 named Impact Player substitutes."""
        if len(pool) > 5:
            raise ValueError("Impact Player pool can have at most 5 players")
        self._impact_pool = list(pool)

    def get_impact_pool(self) -> list[str]:
        """Return Impact Player pool."""
        return list(self._impact_pool)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_available_players(self) -> list[dict[str, Any]]:
        """Return all squad players with 'confirmed' status."""
        return [
            p for p in self._squad
            if self._availability.get(p.get("name", ""), STATUS_CONFIRMED) == STATUS_CONFIRMED
        ]

    def get_probable_xi(self) -> list[dict[str, Any]]:
        """
        Return probable playing XI based on availability.

        If confirmed XI is set, return those players.
        Otherwise, return first 11 available players from squad.
        """
        if self._playing_xi:
            player_map = {p["name"]: p for p in self._squad}
            return [player_map[name] for name in self._playing_xi if name in player_map]

        available = self.get_available_players()
        return available[:11]

    def get_foreign_count_in_xi(self) -> int:
        """Return count of foreign (overseas) players in the playing XI."""
        xi = self.get_probable_xi()
        return sum(1 for p in xi if p.get("is_foreign", False))

    def can_use_foreign_impact_player(self) -> bool:
        """Check if a foreign Impact Player can be used (max 4 foreign in XI)."""
        return self.get_foreign_count_in_xi() < 4

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "team": self._team,
            "squad_size": len(self._squad),
            "playing_xi": self._playing_xi,
            "impact_pool": self._impact_pool,
            "availability": dict(self._availability),
            "injuries": list(self._injury_log),
        }

    @property
    def team(self) -> str:
        return self._team

    def __repr__(self) -> str:
        return f"SquadManager(team={self._team!r}, squad_size={len(self._squad)})"
