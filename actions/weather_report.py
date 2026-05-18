from __future__ import annotations

from datetime import date, datetime, timedelta
import re

import requests


_SOURCE_NAME = "Open-Meteo"
_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_REQUEST_TIMEOUT = 12

_WEEKDAY_ALIASES = {
    0: {"mon", "monday", "monday's", "понедельник", "пн"},
    1: {"tue", "tues", "tuesday", "вторник", "вт"},
    2: {"wed", "wednesday", "среда", "ср"},
    3: {"thu", "thur", "thurs", "thursday", "четверг", "чт"},
    4: {"fri", "friday", "пятница", "пт"},
    5: {"sat", "saturday", "суббота", "сб"},
    6: {"sun", "sunday", "воскресенье", "вс"},
}

_WEATHER_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "rime fog",
    51: "light drizzle",
    53: "drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "dense freezing drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "rain showers",
    81: "heavy rain showers",
    82: "violent rain showers",
    85: "snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "severe thunderstorm with hail",
}


def _fetch_json(url: str, params: dict) -> dict:
    response = requests.get(
        url,
        params=params,
        timeout=_REQUEST_TIMEOUT,
        headers={"User-Agent": "JARVIS Weather/1.0"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Weather service returned an unexpected payload.")
    return payload


def _format_location(result: dict) -> str:
    parts = []
    for key in ("name", "admin1", "country"):
        value = str(result.get(key, "") or "").strip()
        if value and value not in parts:
            parts.append(value)
    return ", ".join(parts) or str(result.get("name", "Unknown location"))


def _geocode_city(city: str) -> dict:
    data = _fetch_json(
        _GEOCODING_URL,
        {
            "name": city,
            "count": 5,
            "language": "en",
            "format": "json",
        },
    )
    results = data.get("results") or []
    if not results:
        raise ValueError(f"Could not find a location for '{city}'.")
    best = results[0]
    return {
        "label": _format_location(best),
        "latitude": best["latitude"],
        "longitude": best["longitude"],
    }


def _normalize_when(value: str) -> str:
    lowered = (value or "today").strip().casefold()
    lowered = re.sub(r"[,\.\!]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip()


def _next_weekday(today: date, target_weekday: int) -> date:
    delta = (target_weekday - today.weekday()) % 7
    return today + timedelta(days=delta)


def _parse_explicit_date(raw: str, today: date) -> date | None:
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    for fmt in ("%d.%m", "%d/%m", "%d-%m"):
        try:
            parsed = datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
        year = today.year
        candidate = date(year, parsed.month, parsed.day)
        if candidate < today:
            candidate = date(year + 1, parsed.month, parsed.day)
        return candidate

    return None


def _parse_requested_dates(when: str, today: date | None = None) -> tuple[list[date], str]:
    today = today or date.today()
    normalized = _normalize_when(when)

    if not normalized or normalized in {"today", "now", "сегодня", "сейчас"}:
        return [today], f"today ({today.isoformat()})"

    if normalized in {"tomorrow", "завтра"}:
        target = today + timedelta(days=1)
        return [target], f"tomorrow ({target.isoformat()})"

    if normalized in {"this weekend", "weekend", "на выходных", "выходные"}:
        if today.weekday() == 5:
            dates = [today, today + timedelta(days=1)]
        elif today.weekday() == 6:
            dates = [today]
        else:
            saturday = _next_weekday(today, 5)
            dates = [saturday, saturday + timedelta(days=1)]
        label = ", ".join(d.isoformat() for d in dates)
        return dates, f"weekend ({label})"

    explicit = _parse_explicit_date(normalized, today)
    if explicit:
        return [explicit], explicit.isoformat()

    for weekday, aliases in _WEEKDAY_ALIASES.items():
        if normalized in aliases:
            target = _next_weekday(today, weekday)
            return [target], f"{normalized} ({target.isoformat()})"

    return [today], f"today ({today.isoformat()})"


def _get_forecast(location: dict) -> dict:
    return _fetch_json(
        _FORECAST_URL,
        {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "current": ",".join(
                [
                    "temperature_2m",
                    "apparent_temperature",
                    "weather_code",
                    "wind_speed_10m",
                    "precipitation",
                ]
            ),
            "daily": ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_probability_max",
                    "wind_speed_10m_max",
                ]
            ),
            "timezone": "auto",
            "forecast_days": 16,
        },
    )


def _round_metric(value) -> str | None:
    if value is None:
        return None
    try:
        return str(int(round(float(value))))
    except Exception:
        return None


def _daily_index_map(forecast: dict) -> dict[str, int]:
    times = ((forecast.get("daily") or {}).get("time")) or []
    return {str(day): idx for idx, day in enumerate(times)}


def _describe_daily(forecast: dict, index: int) -> str:
    daily = forecast.get("daily") or {}
    code = ((daily.get("weather_code") or [None]) + [None])[index]
    high = _round_metric(((daily.get("temperature_2m_max") or [None]) + [None])[index])
    low = _round_metric(((daily.get("temperature_2m_min") or [None]) + [None])[index])
    precip = _round_metric(((daily.get("precipitation_probability_max") or [None]) + [None])[index])
    wind = _round_metric(((daily.get("wind_speed_10m_max") or [None]) + [None])[index])

    parts = [_WEATHER_CODES.get(code, "unknown conditions")]
    if high is not None:
        parts.append(f"high {high}C")
    if low is not None:
        parts.append(f"low {low}C")
    if precip is not None:
        parts.append(f"precipitation chance {precip}%")
    if wind is not None:
        parts.append(f"wind up to {wind} km/h")
    return ", ".join(parts)


def _describe_current(forecast: dict) -> str:
    current = forecast.get("current") or {}
    temp = _round_metric(current.get("temperature_2m"))
    feels_like = _round_metric(current.get("apparent_temperature"))
    wind = _round_metric(current.get("wind_speed_10m"))
    precipitation = _round_metric(current.get("precipitation"))
    code = current.get("weather_code")

    parts = []
    if temp is not None:
        parts.append(f"{temp}C")
    if feels_like is not None:
        parts.append(f"feels like {feels_like}C")
    if code is not None:
        parts.append(_WEATHER_CODES.get(code, "unknown conditions"))
    if wind is not None:
        parts.append(f"wind {wind} km/h")
    if precipitation is not None and precipitation != "0":
        parts.append(f"precipitation {precipitation} mm")
    return ", ".join(parts)


def _build_weather_message(location: dict, forecast: dict, when: str) -> str:
    requested_dates, label = _parse_requested_dates(when)
    daily_lookup = _daily_index_map(forecast)

    if len(requested_dates) == 1:
        target = requested_dates[0]
        idx = daily_lookup.get(target.isoformat())
        if idx is None:
            raise ValueError(f"No forecast is available for {target.isoformat()} yet.")

        daily_summary = _describe_daily(forecast, idx)
        if target == date.today():
            current_summary = _describe_current(forecast)
            if current_summary:
                return (
                    f"Current weather in {location['label']}: {current_summary}. "
                    f"Forecast for {label}: {daily_summary}. "
                    f"Source: {_SOURCE_NAME}."
                )

        return (
            f"Forecast for {location['label']} on {target.isoformat()}: {daily_summary}. "
            f"Source: {_SOURCE_NAME}."
        )

    chunks = []
    for target in requested_dates:
        idx = daily_lookup.get(target.isoformat())
        if idx is None:
            continue
        chunks.append(f"{target.isoformat()}: {_describe_daily(forecast, idx)}")

    if not chunks:
        raise ValueError("No forecast is available for the requested dates.")

    return (
        f"Forecast for {location['label']} over {label}: "
        + " | ".join(chunks)
        + f". Source: {_SOURCE_NAME}."
    )


def weather_action(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    city = parameters.get("city")
    when = parameters.get("time", "today")

    if not city or not isinstance(city, str) or not city.strip():
        msg = "The city is missing for the weather report."
        _log(msg, player)
        return msg

    city = city.strip()
    when = (when or "today").strip()

    try:
        location = _geocode_city(city)
        forecast = _get_forecast(location)
        msg = _build_weather_message(location, forecast, when)
    except Exception as e:
        msg = f"Weather lookup failed for {city}: {e}"
        _log(msg, player)
        return msg

    _log(msg, player)

    if session_memory:
        try:
            session_memory.set_last_search(query=f"weather in {city} {when}", response=msg)
        except Exception:
            pass

    return msg


def _log(message: str, player=None) -> None:
    print(f"[Weather] {message}")
    if player:
        try:
            player.write_log(f"JARVIS: {message}")
        except Exception:
            pass
