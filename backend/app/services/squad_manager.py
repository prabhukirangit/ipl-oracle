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
        {"name": "Hardik Pandya", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1993, "ipl_debut_year": 2015, "personality": "fearless, explosive, confident, swagger, big-match finisher"},
        {"name": "Rohit Sharma", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 1987, "ipl_debut_year": 2008, "personality": "elegant, timing-based, laid-back, devastating when set, loves pull shot"},
        {"name": "Suryakumar Yadav", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 1990, "ipl_debut_year": 2012, "personality": "audacious, 360-degree, unorthodox, flamboyant, risk-taker"},
        {"name": "Jasprit Bumrah", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1993, "ipl_debut_year": 2013, "personality": "ice-cold, cerebral, deceptive yorker specialist, unplayable at death"},
        {"name": "Tilak Varma", "role": "batsman", "batting_style": "left_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 2002, "ipl_debut_year": 2022, "personality": "composed beyond years, adaptable, fearless youngster, clean striker"},
        {"name": "Trent Boult", "role": "bowler", "batting_style": "right_hand", "bowling_style": "left_arm_pace", "is_foreign": True, "birth_year": 1989, "ipl_debut_year": 2017, "personality": "swing master, crafty, calm under pressure, wicket-taker with new ball"},
        {"name": "Quinton de Kock", "role": "wicketkeeper", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1992, "ipl_debut_year": 2012, "personality": "aggressive opener, free-flowing, punishes pace, flat-track bully"},
        {"name": "Will Jacks", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1998, "ipl_debut_year": 2024, "personality": "explosive, fearless, power-hitting allrounder, aggressive off-spinner"},
        {"name": "Deepak Chahar", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1992, "ipl_debut_year": 2014, "personality": "swing specialist, disciplined, economical, lower-order hitter"},
        {"name": "Mitchell Santner", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": True, "birth_year": 1992, "ipl_debut_year": 2018, "personality": "composed, accurate left-arm spin, tactical, cool-headed"},
        {"name": "Naman Dhir", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 2003, "ipl_debut_year": 2024, "personality": "aggressive youngster, fearless, power-hitter, raw talent"},
        {"name": "Sherfane Rutherford", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1998, "ipl_debut_year": 2019, "personality": "powerful, athletic, big-hitting, inconsistent but devastating"},
        {"name": "Ryan Rickelton", "role": "batsman", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1996, "ipl_debut_year": 2025, "personality": "patient, technically sound, elegant left-hander, accumulator"},
        {"name": "Robin Minz", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2003, "ipl_debut_year": 2025, "personality": "energetic, quick-gloved, aggressive keeper-batsman, fearless"},
        {"name": "Shardul Thakur", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1991, "ipl_debut_year": 2015, "personality": "whole-hearted, aggressive seamer, useful lower-order bat, fiery"},
        {"name": "Corbin Bosch", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1998, "ipl_debut_year": 2025, "personality": "disciplined, seam-bowling allrounder, steady, reliable"},
        {"name": "Allah Ghazanfar", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 2005, "ipl_debut_year": 2025, "personality": "prodigious young spinner, deceptive, confident, fearless"},
        {"name": "Raj Angad Bawa", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 2002, "ipl_debut_year": 2022, "personality": "tall, seam-bowling allrounder, composed, developing talent"},
    ],
    "Chennai Super Kings": [
        {"name": "Ruturaj Gaikwad", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 1997, "ipl_debut_year": 2019, "personality": "elegant, technically refined, patient accumulator, classical stroke-maker"},
        {"name": "Sanju Samson", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1994, "ipl_debut_year": 2013, "personality": "mercurial, breathtaking when on song, inconsistent, high-risk high-reward"},
        {"name": "MS Dhoni", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1981, "ipl_debut_year": 2008, "personality": "ice-cold finisher, legendary calm, helicopter shot, reads bowlers like books"},
        {"name": "Shivam Dube", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1993, "ipl_debut_year": 2019, "personality": "big-hitting, muscular, devastating against spin, limited footwork"},
        {"name": "Sarfaraz Khan", "role": "batsman", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": False, "birth_year": 1997, "ipl_debut_year": 2015, "personality": "unorthodox, street-smart, pressure absorber, wristy player"},
        {"name": "Khaleel Ahmed", "role": "bowler", "batting_style": "right_hand", "bowling_style": "left_arm_pace", "is_foreign": False, "birth_year": 1998, "ipl_debut_year": 2018, "personality": "left-arm pace, aggressive, wicket-taker, can be expensive"},
        {"name": "Rahul Chahar", "role": "bowler", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": False, "birth_year": 1999, "ipl_debut_year": 2018, "personality": "attacking leg-spinner, flight and guile, wicket-taking intent"},
        {"name": "Noor Ahmad", "role": "bowler", "batting_style": "right_hand", "bowling_style": "left_arm_spin", "is_foreign": True, "birth_year": 2005, "ipl_debut_year": 2024, "personality": "prodigious young left-arm spinner, fearless, accurate, mature beyond years"},
        {"name": "Nathan Ellis", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1994, "ipl_debut_year": 2022, "personality": "death-bowling specialist, calm, clever variations, yorker expert"},
        {"name": "Dewald Brevis", "role": "batsman", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": True, "birth_year": 2003, "ipl_debut_year": 2022, "personality": "fearless power-hitter, audacious, Baby AB, unorthodox"},
        {"name": "Jamie Overton", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1994, "ipl_debut_year": 2025, "personality": "powerful, aggressive seamer, big-hitting tailender, hostile"},
        {"name": "Matthew Short", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1997, "ipl_debut_year": 2026, "personality": "aggressive opener, clean striker, handy off-spin, athletic"},
        {"name": "Mukesh Choudhary", "role": "bowler", "batting_style": "right_hand", "bowling_style": "left_arm_pace", "is_foreign": False, "birth_year": 1997, "ipl_debut_year": 2022, "personality": "left-arm swing, disciplined, powerplay specialist, steady"},
        {"name": "Shreyas Gopal", "role": "bowler", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": False, "birth_year": 1993, "ipl_debut_year": 2014, "personality": "wily leg-spinner, clever variations, thinking bowler, competitive"},
        {"name": "Ayush Mhatre", "role": "batsman", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2007, "ipl_debut_year": 2025, "personality": "prodigious teen talent, fearless, explosive, raw aggression"},
        {"name": "Matt Henry", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1991, "ipl_debut_year": 2023, "personality": "disciplined seamer, swing artist, new-ball threat, steady"},
    ],
    "Royal Challengers Bengaluru": [
        {"name": "Rajat Patidar", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 1993, "ipl_debut_year": 2021, "personality": "explosive, clean ball-striker, big-match performer, fearless"},
        {"name": "Virat Kohli", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 1988, "ipl_debut_year": 2008, "personality": "intense, relentless, chase-master, feeds off pressure, never gives up"},
        {"name": "Phil Salt", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1996, "ipl_debut_year": 2023, "personality": "explosive opener, devastating power, fast scorer, aggressive intent"},
        {"name": "Jacob Bethell", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": True, "birth_year": 2003, "ipl_debut_year": 2025, "personality": "composed young talent, elegant left-hander, spin-bowling allrounder"},
        {"name": "Tim David", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1996, "ipl_debut_year": 2022, "personality": "six-hitting machine, death-overs specialist, powerful, calm finisher"},
        {"name": "Krunal Pandya", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 1991, "ipl_debut_year": 2016, "personality": "experienced, tactical spinner, composed bat, competitive"},
        {"name": "Josh Hazlewood", "role": "bowler", "batting_style": "left_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1991, "ipl_debut_year": 2020, "personality": "metronomic, disciplined, seam-and-swing, miserly line-and-length"},
        {"name": "Nuwan Thushara", "role": "bowler", "batting_style": "right_hand", "bowling_style": "left_arm_pace", "is_foreign": True, "birth_year": 1995, "ipl_debut_year": 2024, "personality": "raw pace, left-arm variety, aggressive, wicket-taker"},
        {"name": "Rasikh Dar", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 2001, "ipl_debut_year": 2019, "personality": "express pace, aggressive young quick, fiery, improving"},
        {"name": "Bhuvneshwar Kumar", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1990, "ipl_debut_year": 2011, "personality": "master of swing, disciplined, experienced, canny operator"},
        {"name": "Romario Shepherd", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1994, "ipl_debut_year": 2022, "personality": "powerful allrounder, big-hitting, seam-bowling, athletic"},
        {"name": "Devdutt Padikkal", "role": "batsman", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2000, "ipl_debut_year": 2020, "personality": "elegant left-hander, graceful stroke-maker, classical, patient"},
        {"name": "Jitesh Sharma", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1994, "ipl_debut_year": 2022, "personality": "aggressive keeper-batsman, destructive cameos, fearless, quick hands"},
        {"name": "Venkatesh Iyer", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1994, "ipl_debut_year": 2021, "personality": "tall, powerful left-hander, bowling allrounder, confident"},
        {"name": "Suyash Sharma", "role": "bowler", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": False, "birth_year": 2003, "ipl_debut_year": 2023, "personality": "young leg-spinner, deceptive googly, developing, confident"},
        {"name": "Swapnil Singh", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 1993, "ipl_debut_year": 2022, "personality": "steady left-arm spinner, disciplined, economical, reliable"},
    ],
    "Kolkata Knight Riders": [
        {"name": "Ajinkya Rahane", "role": "batsman", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1988, "ipl_debut_year": 2008, "personality": "technically sound, classical, anchor, experienced, calm"},
        {"name": "Rinku Singh", "role": "batsman", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1997, "ipl_debut_year": 2018, "personality": "clutch finisher, fearless, ice-cold in death overs, street-smart"},
        {"name": "Sunil Narine", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1988, "ipl_debut_year": 2012, "personality": "mystery spinner, destructive opener, enigmatic, match-winner"},
        {"name": "Varun Chakravarthy", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 1991, "ipl_debut_year": 2019, "personality": "mystery spinner, deceptive variations, cerebral, wicket-taker"},
        {"name": "Harshit Rana", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 2002, "ipl_debut_year": 2024, "personality": "raw pace, aggressive youngster, bouncer specialist, fiery"},
        {"name": "Cameron Green", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1999, "ipl_debut_year": 2023, "personality": "complete allrounder, tall, powerful, elegant, multi-dimensional"},
        {"name": "Matheesha Pathirana", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 2002, "ipl_debut_year": 2023, "personality": "slingy yorker specialist, Malinga-like, deceptive, death-bowling genius"},
        {"name": "Rachin Ravindra", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": True, "birth_year": 1999, "ipl_debut_year": 2024, "personality": "composed left-hander, technically solid, handy left-arm spin, calm"},
        {"name": "Finn Allen", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1999, "ipl_debut_year": 2022, "personality": "explosive opener, fearless, rapid scorer, power-hitting specialist"},
        {"name": "Angkrish Raghuvanshi", "role": "batsman", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2004, "ipl_debut_year": 2023, "personality": "promising youngster, aggressive, raw talent, stroke-player"},
        {"name": "Ramandeep Singh", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1997, "ipl_debut_year": 2022, "personality": "athletic, power-hitting lower-order bat, seam-bowling, energetic"},
        {"name": "Manish Pandey", "role": "batsman", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1989, "ipl_debut_year": 2008, "personality": "elegant, technically refined, anchor, sometimes slow starter"},
        {"name": "Rovman Powell", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1993, "ipl_debut_year": 2022, "personality": "brute-force power-hitter, six-machine, athletic, high-risk"},
        {"name": "Rahul Tripathi", "role": "batsman", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": False, "birth_year": 1990, "ipl_debut_year": 2017, "personality": "innovative, sweep specialist, unorthodox, busy accumulator"},
        {"name": "Vaibhav Arora", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1998, "ipl_debut_year": 2022, "personality": "disciplined seamer, swing bowler, steady, reliable"},
        {"name": "Umran Malik", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 2000, "ipl_debut_year": 2021, "personality": "express pace, raw speed, aggressive, erratic but dangerous"},
        {"name": "Blessing Muzarabani", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1996, "ipl_debut_year": 2026, "personality": "tall seamer, steep bounce, hostile, wicket-taking threat"},
    ],
    "Delhi Capitals": [
        {"name": "Axar Patel", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 1994, "ipl_debut_year": 2014, "personality": "consistent, accurate left-arm spin, handy lower-order bat, reliable"},
        {"name": "KL Rahul", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1992, "ipl_debut_year": 2013, "personality": "elegant, technically flawless, accumulator, sometimes too cautious"},
        {"name": "Mitchell Starc", "role": "bowler", "batting_style": "left_hand", "bowling_style": "left_arm_pace", "is_foreign": True, "birth_year": 1990, "ipl_debut_year": 2015, "personality": "left-arm express pace, devastating yorkers, big-match bowler, aggressive"},
        {"name": "Kuldeep Yadav", "role": "bowler", "batting_style": "left_hand", "bowling_style": "legbreak", "is_foreign": False, "birth_year": 1994, "ipl_debut_year": 2012, "personality": "wrist-spin wizard, deceptive, flight and turn, wicket-taker"},
        {"name": "Karun Nair", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 1991, "ipl_debut_year": 2013, "personality": "technically sound, patient accumulator, domestic run-machine, classical"},
        {"name": "Tristan Stubbs", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 2001, "ipl_debut_year": 2023, "personality": "powerful youngster, explosive, big-hitting, athletic fielder"},
        {"name": "David Miller", "role": "batsman", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1989, "ipl_debut_year": 2012, "personality": "cool finisher, killer instinct, left-hand power, ice-cold in chases"},
        {"name": "T Natarajan", "role": "bowler", "batting_style": "right_hand", "bowling_style": "left_arm_pace", "is_foreign": False, "birth_year": 1991, "ipl_debut_year": 2017, "personality": "yorker specialist, left-arm variety, calm, death-bowling expert"},
        {"name": "Abishek Porel", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2001, "ipl_debut_year": 2023, "personality": "aggressive keeper-batsman, fearless youngster, clean hitter"},
        {"name": "Lungi Ngidi", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1996, "ipl_debut_year": 2018, "personality": "tall, hostile pace, bounce extractor, aggressive, wicket-taker"},
        {"name": "Ben Duckett", "role": "batsman", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1994, "ipl_debut_year": 2026, "personality": "aggressive left-hand opener, reverse-sweep master, fearless, unorthodox"},
        {"name": "Pathum Nissanka", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1998, "ipl_debut_year": 2026, "personality": "elegant, classical stroke-maker, composed, technically gifted"},
        {"name": "Sameer Rizvi", "role": "batsman", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2003, "ipl_debut_year": 2024, "personality": "young power-hitter, fearless, aggressive, raw talent"},
        {"name": "Dushmantha Chameera", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1992, "ipl_debut_year": 2021, "personality": "express pace, aggressive, hostile, injury-prone but dangerous"},
        {"name": "Kyle Jamieson", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1994, "ipl_debut_year": 2021, "personality": "tall seamer, bounce and carry, batting ability, disciplined"},
    ],
    "Sunrisers Hyderabad": [
        {"name": "Pat Cummins", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1993, "ipl_debut_year": 2014, "personality": "captain-leader, disciplined, competitive, big-match bowler, composed"},
        {"name": "Ishan Kishan", "role": "wicketkeeper", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1998, "ipl_debut_year": 2018, "personality": "explosive left-hander, aggressive opener, powerful, inconsistent"},
        {"name": "Travis Head", "role": "batsman", "batting_style": "left_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1993, "ipl_debut_year": 2020, "personality": "ultra-aggressive, match-winning opener, devastating when set, fearless"},
        {"name": "Heinrich Klaasen", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1991, "ipl_debut_year": 2023, "personality": "destructive against spin, power-hitter, explosive middle-order, match-winner"},
        {"name": "Abhishek Sharma", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 2000, "ipl_debut_year": 2020, "personality": "aggressive left-hand opener, power-hitter, handy spin, confidence player"},
        {"name": "Nitish Kumar Reddy", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 2003, "ipl_debut_year": 2024, "personality": "composed young allrounder, mature, powerful hitter, medium-pace"},
        {"name": "Harshal Patel", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1990, "ipl_debut_year": 2012, "personality": "death-bowling specialist, slower-ball expert, clever, tactical"},
        {"name": "Brydon Carse", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1995, "ipl_debut_year": 2025, "personality": "aggressive seam-bowling allrounder, pace and bounce, hard-hitting"},
        {"name": "Kamindu Mendis", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1998, "ipl_debut_year": 2025, "personality": "versatile, ambidextrous spinner, compact batsman, unique"},
        {"name": "Liam Livingstone", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": True, "birth_year": 1993, "ipl_debut_year": 2019, "personality": "fearless, power-hitting allrounder, leg-spin, explosive, unpredictable"},
        {"name": "Jaydev Unadkat", "role": "bowler", "batting_style": "left_hand", "bowling_style": "left_arm_pace", "is_foreign": False, "birth_year": 1991, "ipl_debut_year": 2010, "personality": "experienced left-arm seamer, swing artist, reliable, economical"},
        {"name": "Shivam Mavi", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 2000, "ipl_debut_year": 2018, "personality": "raw pace, aggressive young quick, improving, inconsistent"},
        {"name": "Zeeshan Ansari", "role": "bowler", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 2003, "ipl_debut_year": 2024, "personality": "young left-arm spinner, developing talent, steady, disciplined"},
        {"name": "Jack Edwards", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1997, "ipl_debut_year": 2026, "personality": "athletic allrounder, composed, clean striker, disciplined medium-pace"},
    ],
    "Rajasthan Royals": [
        {"name": "Riyan Parag", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 2001, "ipl_debut_year": 2019, "personality": "confident, aggressive youngster, flamboyant, handy off-spin, fearless"},
        {"name": "Yashasvi Jaiswal", "role": "batsman", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 2001, "ipl_debut_year": 2020, "personality": "prodigious talent, elegant left-hander, aggressive opener, composed"},
        {"name": "Shimron Hetmyer", "role": "batsman", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1996, "ipl_debut_year": 2019, "personality": "explosive left-hander, power-hitting, laid-back, devastating in bursts"},
        {"name": "Dhruv Jurel", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2002, "ipl_debut_year": 2023, "personality": "gritty, determined, gutsy keeper-batsman, temperament beyond years"},
        {"name": "Ravindra Jadeja", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 1988, "ipl_debut_year": 2008, "personality": "legendary all-round athlete, sharp fielder, composed bat, accurate spin"},
        {"name": "Sam Curran", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_pace", "is_foreign": True, "birth_year": 1998, "ipl_debut_year": 2019, "personality": "competitive allrounder, whole-hearted, clever left-arm seam, clutch performer"},
        {"name": "Jofra Archer", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1995, "ipl_debut_year": 2018, "personality": "express pace, silky smooth, ice-cold, devastating bouncer, match-winner"},
        {"name": "Ravi Bishnoi", "role": "bowler", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": False, "birth_year": 2000, "ipl_debut_year": 2020, "personality": "aggressive leg-spinner, sharp googly, athletic fielder, competitive"},
        {"name": "Tushar Deshpande", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1994, "ipl_debut_year": 2020, "personality": "aggressive seamer, death-bowling, wholehearted, improving"},
        {"name": "Vaibhav Suryavanshi", "role": "batsman", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2010, "ipl_debut_year": 2025, "personality": "prodigious teen talent, youngest IPL player, fearless, raw aggression"},
        {"name": "Lhuan-dre Pretorius", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_pace", "is_foreign": True, "birth_year": 2001, "ipl_debut_year": 2025, "personality": "powerful left-arm seam, hard-hitting bat, athletic, aggressive"},
        {"name": "Kwena Maphaka", "role": "bowler", "batting_style": "left_hand", "bowling_style": "left_arm_pace", "is_foreign": True, "birth_year": 2007, "ipl_debut_year": 2025, "personality": "raw young left-arm pace, express speed, fearless, developing"},
        {"name": "Donovan Ferreira", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1999, "ipl_debut_year": 2025, "personality": "aggressive keeper-batsman, powerful, clean striker, athletic"},
        {"name": "Nandre Burger", "role": "bowler", "batting_style": "right_hand", "bowling_style": "left_arm_pace", "is_foreign": True, "birth_year": 1998, "ipl_debut_year": 2025, "personality": "disciplined left-arm seamer, wicket-taker, steady, reliable"},
        {"name": "Shubham Dubey", "role": "batsman", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2001, "ipl_debut_year": 2024, "personality": "aggressive middle-order bat, powerful, clean hitter, developing"},
    ],
    "Punjab Kings": [
        {"name": "Shreyas Iyer", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 1994, "ipl_debut_year": 2015, "personality": "elegant, composed, captain-material, technically sound, loves spin"},
        {"name": "Marcus Stoinis", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1989, "ipl_debut_year": 2016, "personality": "powerful allrounder, big-hitting, disciplined seam, competitive"},
        {"name": "Arshdeep Singh", "role": "bowler", "batting_style": "left_hand", "bowling_style": "left_arm_pace", "is_foreign": False, "birth_year": 1999, "ipl_debut_year": 2019, "personality": "death-bowling specialist, left-arm swing, yorker expert, ice-cold"},
        {"name": "Marco Jansen", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_pace", "is_foreign": True, "birth_year": 1999, "ipl_debut_year": 2022, "personality": "tall left-arm seamer, bounce and pace, batting ability, aggressive"},
        {"name": "Lockie Ferguson", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1991, "ipl_debut_year": 2019, "personality": "express pace, raw speed, aggressive, bouncer specialist, fiery"},
        {"name": "Yuzvendra Chahal", "role": "bowler", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": False, "birth_year": 1990, "ipl_debut_year": 2011, "personality": "master leg-spinner, flight and guile, match-winner, foxes batsmen"},
        {"name": "Azmatullah Omarzai", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1999, "ipl_debut_year": 2024, "personality": "aggressive allrounder, powerful hitting, seam bowling, competitive"},
        {"name": "Prabhsimran Singh", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2000, "ipl_debut_year": 2019, "personality": "aggressive opener, explosive power, fearless, inconsistent"},
        {"name": "Shashank Singh", "role": "batsman", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1993, "ipl_debut_year": 2022, "personality": "calm finisher, composed under pressure, clean hitting, reliable"},
        {"name": "Harpreet Brar", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 1995, "ipl_debut_year": 2021, "personality": "steady left-arm spin, batting ability, disciplined, economical"},
        {"name": "Nehal Wadhera", "role": "batsman", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2002, "ipl_debut_year": 2024, "personality": "powerful middle-order bat, clean striker, aggressive, developing"},
        {"name": "Xavier Bartlett", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1998, "ipl_debut_year": 2025, "personality": "disciplined right-arm seam, death-bowling ability, steady, improving"},
        {"name": "Cooper Connolly", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": True, "birth_year": 2003, "ipl_debut_year": 2026, "personality": "young left-hand bat, handy left-arm spin, composed, talented"},
        {"name": "Vijaykumar Vyshak", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1998, "ipl_debut_year": 2024, "personality": "disciplined seamer, steady, economical, reliable"},
        {"name": "Musheer Khan", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 2004, "ipl_debut_year": 2025, "personality": "talented young allrounder, technically gifted, composed, promising"},
    ],
    "Gujarat Titans": [
        {"name": "Shubman Gill", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 1999, "ipl_debut_year": 2019, "personality": "elegant, technically refined, classical stroke-maker, composed captain"},
        {"name": "Sai Sudharsan", "role": "batsman", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 2001, "ipl_debut_year": 2022, "personality": "graceful left-hander, composed accumulator, mature, classical"},
        {"name": "Rashid Khan", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": True, "birth_year": 1998, "ipl_debut_year": 2017, "personality": "world-class leg-spinner, aggressive bat, competitive, match-winner"},
        {"name": "Mohammed Siraj", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1994, "ipl_debut_year": 2017, "personality": "aggressive seamer, fiery, competitive, wicket-taking intent"},
        {"name": "Jos Buttler", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1990, "ipl_debut_year": 2016, "personality": "devastating opener, fearless, power-hitting genius, big-match player"},
        {"name": "Washington Sundar", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 1999, "ipl_debut_year": 2017, "personality": "reliable off-spinner, composed left-hand bat, disciplined, steady"},
        {"name": "Glenn Phillips", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1996, "ipl_debut_year": 2024, "personality": "explosive, power-hitting, athletic, versatile, handy off-spin"},
        {"name": "Jason Holder", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1991, "ipl_debut_year": 2016, "personality": "experienced allrounder, calm, tactical, disciplined seam, reliable"},
        {"name": "Prasidh Krishna", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1996, "ipl_debut_year": 2018, "personality": "tall seamer, bounce and pace, improving, aggressive"},
        {"name": "Shahrukh Khan", "role": "batsman", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1995, "ipl_debut_year": 2021, "personality": "power-hitter, big-hitting finisher, confident, fearless"},
        {"name": "Rahul Tewatia", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": False, "birth_year": 1993, "ipl_debut_year": 2014, "personality": "clutch finisher, pressure absorber, handy leg-spin, never-say-die"},
        {"name": "Ishant Sharma", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1988, "ipl_debut_year": 2008, "personality": "experienced pace veteran, bounce specialist, tall, disciplined"},
        {"name": "Manav Suthar", "role": "bowler", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 2002, "ipl_debut_year": 2024, "personality": "young left-arm spinner, accurate, developing, steady"},
        {"name": "Kumar Kushagra", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 2001, "ipl_debut_year": 2023, "personality": "aggressive keeper-batsman, athletic, developing, energetic"},
        {"name": "Tom Banton", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1998, "ipl_debut_year": 2026, "personality": "explosive opener, innovative, switch-hit specialist, fearless"},
    ],
    "Lucknow Super Giants": [
        {"name": "Rishabh Pant", "role": "wicketkeeper", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": False, "birth_year": 1997, "ipl_debut_year": 2016, "personality": "audacious, fearless, unorthodox, match-winning, entertainer"},
        {"name": "Nicholas Pooran", "role": "wicketkeeper", "batting_style": "left_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1995, "ipl_debut_year": 2019, "personality": "explosive left-hander, devastating power, aerial specialist, high-risk"},
        {"name": "Mitchell Marsh", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1991, "ipl_debut_year": 2015, "personality": "composed allrounder, big-match performer, captain-material, powerful"},
        {"name": "Aiden Markram", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": True, "birth_year": 1994, "ipl_debut_year": 2022, "personality": "elegant, technically sound, composed, classical, handy off-spin"},
        {"name": "Mayank Yadav", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 2002, "ipl_debut_year": 2024, "personality": "express pace, raw speed, fearless youngster, devastating when fit"},
        {"name": "Avesh Khan", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1996, "ipl_debut_year": 2017, "personality": "aggressive seamer, bouncer specialist, competitive, improving"},
        {"name": "Mohsin Khan", "role": "bowler", "batting_style": "right_hand", "bowling_style": "left_arm_pace", "is_foreign": False, "birth_year": 1998, "ipl_debut_year": 2022, "personality": "disciplined left-arm seamer, swing and accuracy, reliable"},
        {"name": "Wanindu Hasaranga", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "legbreak", "is_foreign": True, "birth_year": 1997, "ipl_debut_year": 2022, "personality": "attacking leg-spinner, wicket-taker, aggressive bat, competitive"},
        {"name": "Ayush Badoni", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 2000, "ipl_debut_year": 2022, "personality": "fearless, innovative, unorthodox stroke-maker, pressure player"},
        {"name": "Mohammed Shami", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": False, "birth_year": 1990, "ipl_debut_year": 2015, "personality": "master seam bowler, deadly accuracy, outswing specialist, experienced"},
        {"name": "Shahbaz Ahmed", "role": "allrounder", "batting_style": "left_hand", "bowling_style": "left_arm_spin", "is_foreign": False, "birth_year": 1994, "ipl_debut_year": 2020, "personality": "steady allrounder, left-arm spin, composed bat, reliable"},
        {"name": "Anrich Nortje", "role": "bowler", "batting_style": "right_hand", "bowling_style": "right_arm_pace", "is_foreign": True, "birth_year": 1993, "ipl_debut_year": 2020, "personality": "express pace, hostile, aggressive, bouncer specialist, fiery"},
        {"name": "Abdul Samad", "role": "batsman", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 2001, "ipl_debut_year": 2020, "personality": "powerful hitter, six-machine, explosive, developing"},
        {"name": "Josh Inglis", "role": "wicketkeeper", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": True, "birth_year": 1995, "ipl_debut_year": 2025, "personality": "technically sound keeper-batsman, aggressive, clean striker, composed"},
        {"name": "Arshin Kulkarni", "role": "allrounder", "batting_style": "right_hand", "bowling_style": "right_arm_offbreak", "is_foreign": False, "birth_year": 2003, "ipl_debut_year": 2025, "personality": "young allrounder, clean striker, handy off-spin, developing"},
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
