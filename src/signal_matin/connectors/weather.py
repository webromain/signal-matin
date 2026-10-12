"""Meteo Open-Meteo, sans cle API."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from ..models import DataSourceStatus, DataState, WeatherBlock, WeatherDay

_CODES = {
    0: "Ciel degage", 1: "Peu nuageux", 2: "Partiellement nuageux",
    3: "Couvert", 45: "Brouillard", 48: "Brouillard givrant",
    51: "Bruine", 53: "Bruine", 55: "Bruine forte", 61: "Pluie faible",
    63: "Pluie", 65: "Pluie forte", 71: "Neige faible", 73: "Neige",
    75: "Neige forte", 80: "Averses", 81: "Averses", 82: "Fortes averses",
    95: "Orage", 96: "Orage et grele", 99: "Orage et grele",
}


def _json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "Signal-Matin/1.0"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def _forecast(daily: dict[str, Any]) -> list[WeatherDay]:
    """Les jours suivants ; une ligne illisible est ignoree sans bloquer la meteo du jour."""
    days: list[WeatherDay] = []
    for index, date in enumerate((daily.get("time") or [])[1:6], start=1):
        try:
            rain = (daily.get("precipitation_probability_max") or [])[index]
            days.append(WeatherDay(
                date=date,
                condition=_CODES.get(int(daily["weather_code"][index]), "Temps variable"),
                low_c=round(float(daily["temperature_2m_min"][index])),
                high_c=round(float(daily["temperature_2m_max"][index])),
                rain_pct=float(rain) if rain is not None else None,
            ))
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return days


def collect_weather(config: dict) -> tuple[WeatherBlock | None, DataSourceStatus]:
    location = str(config.get("location") or "").strip()
    latitude = config.get("latitude")
    longitude = config.get("longitude")
    if latitude is None or longitude is None:
        return None, DataSourceStatus(
            name="Meteo", state=DataState.UNAVAILABLE,
            detail="Coordonnees absentes dans la configuration.",
        )
    params = urllib.parse.urlencode({
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_min,temperature_2m_max,precipitation_probability_max",
        "forecast_days": 6,
        "timezone": "auto",
    })
    try:
        data = _json("https://api.open-meteo.com/v1/forecast?" + params)
        current = data["current"]
        daily = data.get("daily") or {}
        code = int(current.get("weather_code", -1))
        condition = _CODES.get(code, "Temps variable")
        wind = round(float(current.get("wind_speed_10m", 0)))
        low = (daily.get("temperature_2m_min") or [None])[0]
        high = (daily.get("temperature_2m_max") or [None])[0]
        forecast = _forecast(daily)
        wet = any(word in condition.lower() for word in ("pluie", "averse", "bruine", "orage"))
        block = WeatherBlock(
            location=location or "Position configuree",
            condition=condition,
            temperature_c=round(float(current["temperature_2m"])),
            low_c=round(float(low)) if low is not None else None,
            high_c=round(float(high)) if high is not None else None,
            wind_kmh=wind,
            summary=f"{condition}, avec un vent autour de {wind} km/h.",
            advice="Prevois de quoi rester au sec." if wet else "Conditions calmes pour commencer la journee.",
            forecast=forecast,
        )
        return block, DataSourceStatus(
            name="Meteo", state=DataState.LIVE, detail="Open-Meteo", item_count=1,
        )
    except Exception as error:
        return None, DataSourceStatus(
            name="Meteo", state=DataState.UNAVAILABLE,
            detail=f"Open-Meteo indisponible: {type(error).__name__}.",
        )
