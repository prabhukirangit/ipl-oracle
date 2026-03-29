"""
ScheduleManager — IPL 2026 schedule management.

At startup, attempts to scrape live fixtures from ESPNCricinfo.
Falls back to hardcoded IPL 2026 schedule (all 70 league matches).

IPL 2026 season: March 28 – May 31, 2026.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from .match_state_detector import MatchStateDetector, MatchStatus

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# ---------------------------------------------------------------------------
# IPL 2026 Match schedule (all 70 league-stage matches)
# All times are IST (UTC+5:30)
# Source: Wikipedia / ESPNCricinfo / IPLT20.com
# ---------------------------------------------------------------------------

IPL_2026_SCHEDULE: list[dict[str, Any]] = [
    # Match 1 – Opening match
    {"match_id": "IPL2026_M001", "match_number": 1, "team1": "RCB", "team2": "SRH", "venue": "M. Chinnaswamy Stadium, Bengaluru", "city": "Bengaluru", "match_start_time": "2026-03-28T19:30:00+05:30", "match_date": "2026-03-28", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M002", "match_number": 2, "team1": "MI", "team2": "KKR", "venue": "Wankhede Stadium, Mumbai", "city": "Mumbai", "match_start_time": "2026-03-29T19:30:00+05:30", "match_date": "2026-03-29", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M003", "match_number": 3, "team1": "RR", "team2": "CSK", "venue": "ACA Cricket Stadium, Guwahati", "city": "Guwahati", "match_start_time": "2026-03-30T19:30:00+05:30", "match_date": "2026-03-30", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M004", "match_number": 4, "team1": "PBKS", "team2": "GT", "venue": "Maharaja Yadavindra Singh Stadium, Mullanpur", "city": "Mullanpur", "match_start_time": "2026-03-31T19:30:00+05:30", "match_date": "2026-03-31", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M005", "match_number": 5, "team1": "LSG", "team2": "DC", "venue": "Ekana Cricket Stadium, Lucknow", "city": "Lucknow", "match_start_time": "2026-04-01T19:30:00+05:30", "match_date": "2026-04-01", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M006", "match_number": 6, "team1": "KKR", "team2": "SRH", "venue": "Eden Gardens, Kolkata", "city": "Kolkata", "match_start_time": "2026-04-02T19:30:00+05:30", "match_date": "2026-04-02", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M007", "match_number": 7, "team1": "CSK", "team2": "PBKS", "venue": "MA Chidambaram Stadium, Chennai", "city": "Chennai", "match_start_time": "2026-04-03T19:30:00+05:30", "match_date": "2026-04-03", "status": "upcoming", "result": None},
    # Double header — April 4
    {"match_id": "IPL2026_M008", "match_number": 8, "team1": "DC", "team2": "MI", "venue": "Arun Jaitley Stadium, Delhi", "city": "Delhi", "match_start_time": "2026-04-04T15:30:00+05:30", "match_date": "2026-04-04", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M009", "match_number": 9, "team1": "GT", "team2": "RR", "venue": "Narendra Modi Stadium, Ahmedabad", "city": "Ahmedabad", "match_start_time": "2026-04-04T19:30:00+05:30", "match_date": "2026-04-04", "status": "upcoming", "result": None},
    # Double header — April 5
    {"match_id": "IPL2026_M010", "match_number": 10, "team1": "SRH", "team2": "LSG", "venue": "Rajiv Gandhi International Stadium, Hyderabad", "city": "Hyderabad", "match_start_time": "2026-04-05T15:30:00+05:30", "match_date": "2026-04-05", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M011", "match_number": 11, "team1": "RCB", "team2": "CSK", "venue": "M. Chinnaswamy Stadium, Bengaluru", "city": "Bengaluru", "match_start_time": "2026-04-05T19:30:00+05:30", "match_date": "2026-04-05", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M012", "match_number": 12, "team1": "KKR", "team2": "PBKS", "venue": "Eden Gardens, Kolkata", "city": "Kolkata", "match_start_time": "2026-04-06T19:30:00+05:30", "match_date": "2026-04-06", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M013", "match_number": 13, "team1": "RR", "team2": "MI", "venue": "ACA Cricket Stadium, Guwahati", "city": "Guwahati", "match_start_time": "2026-04-07T19:30:00+05:30", "match_date": "2026-04-07", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M014", "match_number": 14, "team1": "DC", "team2": "GT", "venue": "Arun Jaitley Stadium, Delhi", "city": "Delhi", "match_start_time": "2026-04-08T19:30:00+05:30", "match_date": "2026-04-08", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M015", "match_number": 15, "team1": "KKR", "team2": "LSG", "venue": "Eden Gardens, Kolkata", "city": "Kolkata", "match_start_time": "2026-04-09T19:30:00+05:30", "match_date": "2026-04-09", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M016", "match_number": 16, "team1": "RR", "team2": "RCB", "venue": "ACA Cricket Stadium, Guwahati", "city": "Guwahati", "match_start_time": "2026-04-10T19:30:00+05:30", "match_date": "2026-04-10", "status": "upcoming", "result": None},
    # Double header — April 11
    {"match_id": "IPL2026_M017", "match_number": 17, "team1": "PBKS", "team2": "SRH", "venue": "Maharaja Yadavindra Singh Stadium, Mullanpur", "city": "Mullanpur", "match_start_time": "2026-04-11T15:30:00+05:30", "match_date": "2026-04-11", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M018", "match_number": 18, "team1": "CSK", "team2": "DC", "venue": "MA Chidambaram Stadium, Chennai", "city": "Chennai", "match_start_time": "2026-04-11T19:30:00+05:30", "match_date": "2026-04-11", "status": "upcoming", "result": None},
    # Double header — April 12
    {"match_id": "IPL2026_M019", "match_number": 19, "team1": "LSG", "team2": "GT", "venue": "Ekana Cricket Stadium, Lucknow", "city": "Lucknow", "match_start_time": "2026-04-12T15:30:00+05:30", "match_date": "2026-04-12", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M020", "match_number": 20, "team1": "MI", "team2": "RCB", "venue": "Wankhede Stadium, Mumbai", "city": "Mumbai", "match_start_time": "2026-04-12T19:30:00+05:30", "match_date": "2026-04-12", "status": "upcoming", "result": None},
    # Phase 2
    {"match_id": "IPL2026_M021", "match_number": 21, "team1": "SRH", "team2": "RR", "venue": "Rajiv Gandhi International Stadium, Hyderabad", "city": "Hyderabad", "match_start_time": "2026-04-13T19:30:00+05:30", "match_date": "2026-04-13", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M022", "match_number": 22, "team1": "CSK", "team2": "KKR", "venue": "MA Chidambaram Stadium, Chennai", "city": "Chennai", "match_start_time": "2026-04-14T19:30:00+05:30", "match_date": "2026-04-14", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M023", "match_number": 23, "team1": "RCB", "team2": "LSG", "venue": "M. Chinnaswamy Stadium, Bengaluru", "city": "Bengaluru", "match_start_time": "2026-04-15T19:30:00+05:30", "match_date": "2026-04-15", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M024", "match_number": 24, "team1": "MI", "team2": "PBKS", "venue": "Wankhede Stadium, Mumbai", "city": "Mumbai", "match_start_time": "2026-04-16T19:30:00+05:30", "match_date": "2026-04-16", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M025", "match_number": 25, "team1": "GT", "team2": "KKR", "venue": "Narendra Modi Stadium, Ahmedabad", "city": "Ahmedabad", "match_start_time": "2026-04-17T19:30:00+05:30", "match_date": "2026-04-17", "status": "upcoming", "result": None},
    # Double header — April 18
    {"match_id": "IPL2026_M026", "match_number": 26, "team1": "RCB", "team2": "DC", "venue": "M. Chinnaswamy Stadium, Bengaluru", "city": "Bengaluru", "match_start_time": "2026-04-18T15:30:00+05:30", "match_date": "2026-04-18", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M027", "match_number": 27, "team1": "SRH", "team2": "CSK", "venue": "Rajiv Gandhi International Stadium, Hyderabad", "city": "Hyderabad", "match_start_time": "2026-04-18T19:30:00+05:30", "match_date": "2026-04-18", "status": "upcoming", "result": None},
    # Double header — April 19
    {"match_id": "IPL2026_M028", "match_number": 28, "team1": "KKR", "team2": "RR", "venue": "Eden Gardens, Kolkata", "city": "Kolkata", "match_start_time": "2026-04-19T15:30:00+05:30", "match_date": "2026-04-19", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M029", "match_number": 29, "team1": "PBKS", "team2": "LSG", "venue": "Maharaja Yadavindra Singh Stadium, Mullanpur", "city": "Mullanpur", "match_start_time": "2026-04-19T19:30:00+05:30", "match_date": "2026-04-19", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M030", "match_number": 30, "team1": "GT", "team2": "MI", "venue": "Narendra Modi Stadium, Ahmedabad", "city": "Ahmedabad", "match_start_time": "2026-04-20T19:30:00+05:30", "match_date": "2026-04-20", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M031", "match_number": 31, "team1": "SRH", "team2": "DC", "venue": "Rajiv Gandhi International Stadium, Hyderabad", "city": "Hyderabad", "match_start_time": "2026-04-21T19:30:00+05:30", "match_date": "2026-04-21", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M032", "match_number": 32, "team1": "LSG", "team2": "RR", "venue": "Ekana Cricket Stadium, Lucknow", "city": "Lucknow", "match_start_time": "2026-04-22T19:30:00+05:30", "match_date": "2026-04-22", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M033", "match_number": 33, "team1": "MI", "team2": "CSK", "venue": "Wankhede Stadium, Mumbai", "city": "Mumbai", "match_start_time": "2026-04-23T19:30:00+05:30", "match_date": "2026-04-23", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M034", "match_number": 34, "team1": "RCB", "team2": "GT", "venue": "M. Chinnaswamy Stadium, Bengaluru", "city": "Bengaluru", "match_start_time": "2026-04-24T19:30:00+05:30", "match_date": "2026-04-24", "status": "upcoming", "result": None},
    # Double header — April 25
    {"match_id": "IPL2026_M035", "match_number": 35, "team1": "DC", "team2": "PBKS", "venue": "Arun Jaitley Stadium, Delhi", "city": "Delhi", "match_start_time": "2026-04-25T15:30:00+05:30", "match_date": "2026-04-25", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M036", "match_number": 36, "team1": "RR", "team2": "SRH", "venue": "Sawai Mansingh Stadium, Jaipur", "city": "Jaipur", "match_start_time": "2026-04-25T19:30:00+05:30", "match_date": "2026-04-25", "status": "upcoming", "result": None},
    # Double header — April 26
    {"match_id": "IPL2026_M037", "match_number": 37, "team1": "GT", "team2": "CSK", "venue": "Narendra Modi Stadium, Ahmedabad", "city": "Ahmedabad", "match_start_time": "2026-04-26T15:30:00+05:30", "match_date": "2026-04-26", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M038", "match_number": 38, "team1": "LSG", "team2": "KKR", "venue": "Ekana Cricket Stadium, Lucknow", "city": "Lucknow", "match_start_time": "2026-04-26T19:30:00+05:30", "match_date": "2026-04-26", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M039", "match_number": 39, "team1": "DC", "team2": "RCB", "venue": "Arun Jaitley Stadium, Delhi", "city": "Delhi", "match_start_time": "2026-04-27T19:30:00+05:30", "match_date": "2026-04-27", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M040", "match_number": 40, "team1": "PBKS", "team2": "RR", "venue": "Maharaja Yadavindra Singh Stadium, Mullanpur", "city": "Mullanpur", "match_start_time": "2026-04-28T19:30:00+05:30", "match_date": "2026-04-28", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M041", "match_number": 41, "team1": "MI", "team2": "SRH", "venue": "Wankhede Stadium, Mumbai", "city": "Mumbai", "match_start_time": "2026-04-29T19:30:00+05:30", "match_date": "2026-04-29", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M042", "match_number": 42, "team1": "GT", "team2": "RCB", "venue": "Narendra Modi Stadium, Ahmedabad", "city": "Ahmedabad", "match_start_time": "2026-04-30T19:30:00+05:30", "match_date": "2026-04-30", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M043", "match_number": 43, "team1": "RR", "team2": "DC", "venue": "Sawai Mansingh Stadium, Jaipur", "city": "Jaipur", "match_start_time": "2026-05-01T19:30:00+05:30", "match_date": "2026-05-01", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M044", "match_number": 44, "team1": "CSK", "team2": "MI", "venue": "MA Chidambaram Stadium, Chennai", "city": "Chennai", "match_start_time": "2026-05-02T19:30:00+05:30", "match_date": "2026-05-02", "status": "upcoming", "result": None},
    # Double header — May 3
    {"match_id": "IPL2026_M045", "match_number": 45, "team1": "SRH", "team2": "KKR", "venue": "Rajiv Gandhi International Stadium, Hyderabad", "city": "Hyderabad", "match_start_time": "2026-05-03T15:30:00+05:30", "match_date": "2026-05-03", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M046", "match_number": 46, "team1": "GT", "team2": "PBKS", "venue": "Narendra Modi Stadium, Ahmedabad", "city": "Ahmedabad", "match_start_time": "2026-05-03T19:30:00+05:30", "match_date": "2026-05-03", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M047", "match_number": 47, "team1": "MI", "team2": "LSG", "venue": "Wankhede Stadium, Mumbai", "city": "Mumbai", "match_start_time": "2026-05-04T19:30:00+05:30", "match_date": "2026-05-04", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M048", "match_number": 48, "team1": "DC", "team2": "CSK", "venue": "Arun Jaitley Stadium, Delhi", "city": "Delhi", "match_start_time": "2026-05-05T19:30:00+05:30", "match_date": "2026-05-05", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M049", "match_number": 49, "team1": "SRH", "team2": "PBKS", "venue": "Rajiv Gandhi International Stadium, Hyderabad", "city": "Hyderabad", "match_start_time": "2026-05-06T15:30:00+05:30", "match_date": "2026-05-06", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M050", "match_number": 50, "team1": "LSG", "team2": "RCB", "venue": "Ekana Cricket Stadium, Lucknow", "city": "Lucknow", "match_start_time": "2026-05-07T19:30:00+05:30", "match_date": "2026-05-07", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M051", "match_number": 51, "team1": "DC", "team2": "KKR", "venue": "Arun Jaitley Stadium, Delhi", "city": "Delhi", "match_start_time": "2026-05-08T19:30:00+05:30", "match_date": "2026-05-08", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M052", "match_number": 52, "team1": "RR", "team2": "GT", "venue": "Sawai Mansingh Stadium, Jaipur", "city": "Jaipur", "match_start_time": "2026-05-09T19:30:00+05:30", "match_date": "2026-05-09", "status": "upcoming", "result": None},
    # Double header — May 10
    {"match_id": "IPL2026_M053", "match_number": 53, "team1": "CSK", "team2": "LSG", "venue": "MA Chidambaram Stadium, Chennai", "city": "Chennai", "match_start_time": "2026-05-10T15:30:00+05:30", "match_date": "2026-05-10", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M054", "match_number": 54, "team1": "RCB", "team2": "MI", "venue": "Nava Raipur Cricket Stadium, Nava Raipur", "city": "Nava Raipur", "match_start_time": "2026-05-10T19:30:00+05:30", "match_date": "2026-05-10", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M055", "match_number": 55, "team1": "PBKS", "team2": "DC", "venue": "HPCA Cricket Stadium, Dharamshala", "city": "Dharamshala", "match_start_time": "2026-05-11T19:30:00+05:30", "match_date": "2026-05-11", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M056", "match_number": 56, "team1": "GT", "team2": "SRH", "venue": "Narendra Modi Stadium, Ahmedabad", "city": "Ahmedabad", "match_start_time": "2026-05-12T19:30:00+05:30", "match_date": "2026-05-12", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M057", "match_number": 57, "team1": "RCB", "team2": "KKR", "venue": "Nava Raipur Cricket Stadium, Nava Raipur", "city": "Nava Raipur", "match_start_time": "2026-05-13T19:30:00+05:30", "match_date": "2026-05-13", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M058", "match_number": 58, "team1": "PBKS", "team2": "MI", "venue": "HPCA Cricket Stadium, Dharamshala", "city": "Dharamshala", "match_start_time": "2026-05-14T19:30:00+05:30", "match_date": "2026-05-14", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M059", "match_number": 59, "team1": "LSG", "team2": "CSK", "venue": "Ekana Cricket Stadium, Lucknow", "city": "Lucknow", "match_start_time": "2026-05-15T19:30:00+05:30", "match_date": "2026-05-15", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M060", "match_number": 60, "team1": "KKR", "team2": "GT", "venue": "Eden Gardens, Kolkata", "city": "Kolkata", "match_start_time": "2026-05-16T19:30:00+05:30", "match_date": "2026-05-16", "status": "upcoming", "result": None},
    # Double header — May 17
    {"match_id": "IPL2026_M061", "match_number": 61, "team1": "PBKS", "team2": "RCB", "venue": "HPCA Cricket Stadium, Dharamshala", "city": "Dharamshala", "match_start_time": "2026-05-17T15:30:00+05:30", "match_date": "2026-05-17", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M062", "match_number": 62, "team1": "DC", "team2": "RR", "venue": "Arun Jaitley Stadium, Delhi", "city": "Delhi", "match_start_time": "2026-05-17T19:30:00+05:30", "match_date": "2026-05-17", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M063", "match_number": 63, "team1": "CSK", "team2": "SRH", "venue": "MA Chidambaram Stadium, Chennai", "city": "Chennai", "match_start_time": "2026-05-18T19:30:00+05:30", "match_date": "2026-05-18", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M064", "match_number": 64, "team1": "RR", "team2": "LSG", "venue": "Sawai Mansingh Stadium, Jaipur", "city": "Jaipur", "match_start_time": "2026-05-19T19:30:00+05:30", "match_date": "2026-05-19", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M065", "match_number": 65, "team1": "KKR", "team2": "MI", "venue": "Eden Gardens, Kolkata", "city": "Kolkata", "match_start_time": "2026-05-20T19:30:00+05:30", "match_date": "2026-05-20", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M066", "match_number": 66, "team1": "CSK", "team2": "GT", "venue": "MA Chidambaram Stadium, Chennai", "city": "Chennai", "match_start_time": "2026-05-21T19:30:00+05:30", "match_date": "2026-05-21", "status": "upcoming", "result": None},
    # Double header — May 22 (just one marked D/N)
    {"match_id": "IPL2026_M067", "match_number": 67, "team1": "SRH", "team2": "RCB", "venue": "Rajiv Gandhi International Stadium, Hyderabad", "city": "Hyderabad", "match_start_time": "2026-05-22T15:30:00+05:30", "match_date": "2026-05-22", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M068", "match_number": 68, "team1": "LSG", "team2": "PBKS", "venue": "Ekana Cricket Stadium, Lucknow", "city": "Lucknow", "match_start_time": "2026-05-23T19:30:00+05:30", "match_date": "2026-05-23", "status": "upcoming", "result": None},
    # Double header — May 24 (last league day)
    {"match_id": "IPL2026_M069", "match_number": 69, "team1": "MI", "team2": "RR", "venue": "Wankhede Stadium, Mumbai", "city": "Mumbai", "match_start_time": "2026-05-24T15:30:00+05:30", "match_date": "2026-05-24", "status": "upcoming", "result": None},
    {"match_id": "IPL2026_M070", "match_number": 70, "team1": "KKR", "team2": "DC", "venue": "Eden Gardens, Kolkata", "city": "Kolkata", "match_start_time": "2026-05-24T19:30:00+05:30", "match_date": "2026-05-24", "status": "upcoming", "result": None},
]


# ---------------------------------------------------------------------------
# Schedule scraper — fetches live fixtures from ESPNCricinfo at startup
# ---------------------------------------------------------------------------

async def _scrape_schedule_from_espn() -> list[dict[str, Any]] | None:
    """
    Attempt to scrape IPL 2026 schedule from ESPNCricinfo.

    Returns parsed schedule list, or None on failure.
    """
    import httpx

    url = "https://www.espncricinfo.com/series/ipl-2026-1510719/match-schedule-fixtures-and-results"

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            },
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as exc:
        logger.info("Schedule scrape failed (network): %s", exc)
        return None

    # ESPNCricinfo embeds schedule data in a __NEXT_DATA__ JSON blob
    import json as _json, re as _re

    html = resp.text
    m = _re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, _re.DOTALL)
    if not m:
        logger.info("Schedule scrape: __NEXT_DATA__ not found")
        return None

    try:
        next_data = _json.loads(m.group(1))
    except _json.JSONDecodeError:
        logger.info("Schedule scrape: JSON parse failed")
        return None

    # Navigate the nested structure to find match list
    try:
        # ESPNCricinfo structure: props.appPageProps.data.content.matches
        content = next_data["props"]["appPageProps"]["data"]["content"]
        match_list = content.get("matches") or content.get("matchScheduleList", [])
    except (KeyError, TypeError):
        logger.info("Schedule scrape: unexpected JSON structure")
        return None

    if not match_list:
        return None

    _TEAM_ABBREVS = {
        "Royal Challengers Bengaluru": "RCB", "Royal Challengers Bangalore": "RCB",
        "Mumbai Indians": "MI", "Chennai Super Kings": "CSK",
        "Kolkata Knight Riders": "KKR", "Sunrisers Hyderabad": "SRH",
        "Rajasthan Royals": "RR", "Delhi Capitals": "DC",
        "Gujarat Titans": "GT", "Punjab Kings": "PBKS",
        "Lucknow Super Giants": "LSG",
    }

    schedule = []
    for i, match_data in enumerate(match_list, 1):
        try:
            teams = match_data.get("teams", [])
            if len(teams) < 2:
                continue

            t1_full = teams[0].get("team", {}).get("longName", "")
            t2_full = teams[1].get("team", {}).get("longName", "")
            t1 = _TEAM_ABBREVS.get(t1_full, t1_full[:3].upper())
            t2 = _TEAM_ABBREVS.get(t2_full, t2_full[:3].upper())

            ground = match_data.get("ground", {})
            venue_name = ground.get("longName", ground.get("name", "TBD"))
            city = ground.get("town", {}).get("name", "")

            # Parse date from epoch ms
            start_ts = match_data.get("startDate")
            if start_ts:
                dt = datetime.fromtimestamp(int(start_ts) / 1000, tz=IST)
            else:
                start_str = match_data.get("startTime", "")
                dt = datetime.fromisoformat(start_str) if start_str else None

            if dt is None:
                continue

            match_time = dt.isoformat()
            match_date = dt.strftime("%Y-%m-%d")

            status = "upcoming"
            if match_data.get("state") == "POST":
                status = "completed"

            schedule.append({
                "match_id": f"IPL2026_M{i:03d}",
                "match_number": i,
                "team1": t1,
                "team2": t2,
                "venue": f"{venue_name}, {city}" if city else venue_name,
                "city": city,
                "match_start_time": match_time,
                "match_date": match_date,
                "status": status,
                "result": match_data.get("statusText"),
            })
        except Exception:
            continue

    if len(schedule) >= 10:
        logger.info("Schedule scraped from ESPNCricinfo: %d matches", len(schedule))
        return schedule

    return None


class ScheduleManager:
    """
    Manages the IPL 2026 match schedule.

    On init, uses hardcoded schedule. Call refresh() to attempt live scrape.
    """

    def __init__(self) -> None:
        self._detector = MatchStateDetector()
        self._schedule = list(IPL_2026_SCHEDULE)
        self._source = "hardcoded"

    async def refresh(self) -> None:
        """Attempt to scrape live schedule from ESPNCricinfo. Falls back to hardcoded."""
        try:
            scraped = await _scrape_schedule_from_espn()
            if scraped:
                self._schedule = scraped
                self._source = "espncricinfo"
                logger.info("Schedule updated from ESPNCricinfo (%d matches)", len(scraped))
            else:
                logger.info("Schedule scrape returned no data — using hardcoded (%d matches)", len(self._schedule))
        except Exception as exc:
            logger.warning("Schedule refresh failed: %s — using hardcoded", exc)

    @property
    def source(self) -> str:
        return self._source

    def get_today_matches(
        self,
        current_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return all of today's matches (LIVE or FUTURE only — never COMPLETED).
        """
        if current_time is None:
            current_time = datetime.now(IST)

        today_str = current_time.strftime("%Y-%m-%d")

        today_matches = []
        for match in self._schedule:
            if match.get("match_date") == today_str:
                enriched = self._enrich_with_state(match, current_time)
                # Filter out COMPLETED matches per API spec
                if enriched["match_status"] != MatchStatus.COMPLETED:
                    today_matches.append(enriched)

        return today_matches

    def get_upcoming_matches(
        self,
        days: int = 7,
        current_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return upcoming matches in the next N days (excludes COMPLETED).
        """
        if current_time is None:
            current_time = datetime.now(IST)

        upcoming = []
        for match in self._schedule:
            try:
                match_dt = datetime.fromisoformat(match["match_start_time"])
            except (ValueError, KeyError):
                continue

            if match_dt.tzinfo is None:
                match_dt = match_dt.replace(tzinfo=IST)

            diff = match_dt - current_time
            if 0 <= diff.total_seconds() / 3600 / 24 <= days:
                enriched = self._enrich_with_state(match, current_time)
                if enriched["match_status"] != MatchStatus.COMPLETED:
                    upcoming.append(enriched)

        # Sort by match start time
        upcoming.sort(key=lambda m: m.get("match_start_time", ""))
        return upcoming

    def get_all_matches(self) -> list[dict[str, Any]]:
        """Return all matches in the schedule (for admin/debug)."""
        return list(self._schedule)

    def get_match_by_id(self, match_id: str) -> dict[str, Any] | None:
        """Look up a match by ID."""
        for match in self._schedule:
            if match.get("match_id") == match_id:
                return match
        return None

    def _enrich_with_state(
        self,
        match: dict[str, Any],
        current_time: datetime,
    ) -> dict[str, Any]:
        """Add match state and derived fields to a match dict."""
        enriched = dict(match)

        # Detect match state
        status, state_details = self._detector.detect(match, current_time=current_time)
        enriched["match_status"] = status
        enriched["state_details"] = state_details

        # Add display fields
        try:
            match_dt = datetime.fromisoformat(match["match_start_time"])
            enriched["match_time_display"] = match_dt.strftime("%I:%M %p IST")
            enriched["match_date_display"] = match_dt.strftime("%a, %d %b %Y")
        except (ValueError, KeyError):
            enriched["match_time_display"] = "TBD"
            enriched["match_date_display"] = match.get("match_date", "TBD")

        # Add simulatable flag
        enriched["is_simulatable"] = self._detector.is_simulatable(status)

        return enriched

    def get_next_match(self, current_time: datetime | None = None) -> dict[str, Any] | None:
        """Return the next upcoming match."""
        upcoming = self.get_upcoming_matches(days=30, current_time=current_time)
        return upcoming[0] if upcoming else None

    def get_team_matches(
        self,
        team: str,
        upcoming_only: bool = True,
        current_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return all matches for a specific team."""
        if current_time is None:
            current_time = datetime.now(IST)

        all_enriched = [
            self._enrich_with_state(m, current_time)
            for m in self._schedule
            if m.get("team1") == team or m.get("team2") == team
        ]

        if upcoming_only:
            return [
                m for m in all_enriched
                if m["match_status"] != MatchStatus.COMPLETED
            ]
        return all_enriched
