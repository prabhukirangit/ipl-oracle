"""
WeatherService — OpenWeatherMap REST integration.

Fetches current weather conditions at IPL venue coordinates.
Caches per venue per hour (in-memory dict).
Falls back to WeatherAgent DEFAULT_WEATHER if API key is missing or request fails.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Venue coordinates cache (loaded from skills JSON once)
# ---------------------------------------------------------------------------

_SKILLS_DIR = Path(__file__).resolve().parents[4] / "skills"
_VENUE_COORDS_PATH = _SKILLS_DIR / "ipl2026_venue_coords.json"

_venue_coords: dict[str, dict] = {}


def _load_venue_coords() -> dict[str, dict]:
    global _venue_coords
    if _venue_coords:
        return _venue_coords
    try:
        with open(_VENUE_COORDS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        _venue_coords = data.get("venues", {})
    except FileNotFoundError:
        logger.warning("ipl2026_venue_coords.json not found at %s", _VENUE_COORDS_PATH)
        _venue_coords = {}
    return _venue_coords


# ---------------------------------------------------------------------------
# Default weather (compatible with WeatherAgent.DEFAULT_WEATHER)
# ---------------------------------------------------------------------------

DEFAULT_WEATHER: dict[str, Any] = {
    "temperature": 26.0,
    "humidity": 60.0,
    "wind_speed": 10.0,
    "wind_direction": "NE",
    "cloud_cover": 20.0,
    "precipitation": 0.0,
    "dew_point": 18.0,
    "description": "Clear",
    "source": "default_fallback",
    "dew_risk": "low",
    "dew_factor": 1.0,
}

# ---------------------------------------------------------------------------
# Per-hour cache: key = venue_name, value = {"data": dict, "fetched_at": float}
# ---------------------------------------------------------------------------

_weather_cache: dict[str, dict] = {}
_CACHE_TTL_SECONDS = 3600  # 1 hour


def _dew_risk_from_conditions(temp: float, humidity: float, dew_point: float) -> tuple[str, float]:
    """
    Classify dew risk and return a dew_factor (0.7–1.0).

    dew_factor 1.0 = no dew, 0.7 = heavy dew (worst case for spinners).
    """
    dew_depression = temp - dew_point  # smaller gap = more dew likely
    if dew_depression <= 3 and humidity >= 80:
        return "high", 0.72
    elif dew_depression <= 6 and humidity >= 70:
        return "medium", 0.85
    else:
        return "low", 1.0


def _owm_to_weather_agent(raw: dict) -> dict[str, Any]:
    """Convert OpenWeatherMap JSON response to WeatherAgent-compatible dict."""
    main = raw.get("main", {})
    wind = raw.get("wind", {})
    clouds = raw.get("clouds", {})
    rain = raw.get("rain", {})
    weather_desc = raw.get("weather", [{}])[0]

    temp = float(main.get("temp", 26.0))
    humidity = float(main.get("humidity", 60.0))
    dew_point = float(main.get("dew_point", temp - 8.0))

    wind_speed = float(wind.get("speed", 10.0)) * 3.6  # m/s → km/h
    wind_deg = wind.get("deg", 0)
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    wind_dir = directions[int((wind_deg + 22.5) / 45) % 8]

    cloud_cover = float(clouds.get("all", 20.0))
    precipitation = float(rain.get("1h", 0.0))

    dew_risk, dew_factor = _dew_risk_from_conditions(temp, humidity, dew_point)

    return {
        "temperature": round(temp, 1),
        "humidity": round(humidity, 1),
        "wind_speed": round(wind_speed, 1),
        "wind_direction": wind_dir,
        "cloud_cover": round(cloud_cover, 1),
        "precipitation": round(precipitation, 2),
        "dew_point": round(dew_point, 1),
        "description": weather_desc.get("description", "").title(),
        "source": "openweathermap",
        "dew_risk": dew_risk,
        "dew_factor": dew_factor,
    }


async def get_weather_for_venue(venue_name: str) -> dict[str, Any]:
    """
    Fetch current weather for an IPL venue.

    Args:
        venue_name: Exact venue name as in ipl2026_venue_coords.json

    Returns:
        Weather dict compatible with WeatherAgent(weather_data=...).
        Falls back to DEFAULT_WEATHER if API key missing or request fails.
    """
    # Check in-memory cache
    cached = _weather_cache.get(venue_name)
    if cached and (time.time() - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
        logger.debug("Weather cache hit for venue: %s", venue_name)
        return cached["data"]

    api_key = settings.openweathermap_api_key
    if not api_key:
        logger.warning("OpenWeatherMap API key not set — using default weather for %s", venue_name)
        return dict(DEFAULT_WEATHER)

    coords = _load_venue_coords().get(venue_name)
    if not coords:
        logger.warning("Venue '%s' not found in coords JSON — using default weather", venue_name)
        return dict(DEFAULT_WEATHER)

    lat = coords["lat"]
    lon = coords["lng"]
    url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            raw = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error("OWM HTTP error for %s: %s", venue_name, exc)
        return dict(DEFAULT_WEATHER)
    except httpx.RequestError as exc:
        logger.error("OWM request error for %s: %s", venue_name, exc)
        return dict(DEFAULT_WEATHER)

    weather = _owm_to_weather_agent(raw)

    # Store in cache
    _weather_cache[venue_name] = {"data": weather, "fetched_at": time.time()}
    logger.info("Fetched weather for %s: %s°C, dew_risk=%s", venue_name, weather["temperature"], weather["dew_risk"])
    return weather
