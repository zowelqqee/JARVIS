from datetime import date

from actions.weather_report import _parse_requested_dates, weather_action


def test_parse_requested_dates_handles_relative_keywords():
    today = date(2026, 5, 18)

    dates, label = _parse_requested_dates("today", today=today)
    assert dates == [date(2026, 5, 18)]
    assert "2026-05-18" in label

    dates, label = _parse_requested_dates("завтра", today=today)
    assert dates == [date(2026, 5, 19)]
    assert "2026-05-19" in label

    dates, label = _parse_requested_dates("this weekend", today=today)
    assert dates == [date(2026, 5, 23), date(2026, 5, 24)]
    assert "2026-05-23" in label


def test_weather_action_reports_open_meteo_source(monkeypatch):
    today = date.today().isoformat()

    def fake_fetch_json(url: str, params: dict) -> dict:
        if "geocoding-api" in url:
            return {
                "results": [
                    {
                        "name": "Moscow",
                        "admin1": "Moscow",
                        "country": "Russia",
                        "latitude": 55.75,
                        "longitude": 37.62,
                    }
                ]
            }

        return {
            "current": {
                "temperature_2m": 21.4,
                "apparent_temperature": 20.7,
                "weather_code": 2,
                "wind_speed_10m": 11.2,
                "precipitation": 0.0,
            },
            "daily": {
                "time": [today],
                "weather_code": [3],
                "temperature_2m_max": [24.8],
                "temperature_2m_min": [14.1],
                "precipitation_probability_max": [35],
                "wind_speed_10m_max": [18.3],
            },
        }

    monkeypatch.setattr("actions.weather_report._fetch_json", fake_fetch_json)

    result = weather_action({"city": "Moscow", "time": "today"})

    assert "Moscow" in result
    assert "Source: Open-Meteo." in result
