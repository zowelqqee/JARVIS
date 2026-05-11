#flight_finder.py
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from config import is_linux, is_mac, is_windows


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _gemini_client():
    from google import genai

    return genai.Client(api_key=_get_api_key())


_MONTH_MAP: dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "ocak": 1, "subat": 2, "şubat": 2, "mart": 3, "nisan": 4,
    "mayis": 5, "mayıs": 5, "haziran": 6, "temmuz": 7,
    "agustos": 8, "ağustos": 8, "eylul": 9, "eylül": 9,
    "ekim": 10, "kasim": 11, "kasım": 11, "aralik": 12, "aralık": 12,
}

_IATA_RE = re.compile(r"^[A-Z]{3}$")
_INLINE_IATA_RE = re.compile(r"\b([A-Z]{3})\b")
_TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")
_PRICE_RE = re.compile(r"(?:\d[\d\s.,]{2,})(?:\s?(?:₽|руб(?:\.|лей)?|RUB|\$|€|USD|EUR|AED|KZT))", re.IGNORECASE)
_STOP_RE = re.compile(r"без пересад|пересад|stop|stops|direct|non-stop|nonstop", re.IGNORECASE)
_DURATION_RE = re.compile(
    r"(\b\d+\s*(?:ч|час|h)\b.*\b\d+\s*(?:м|min)\b)|(\b\d+\s*(?:h|min|ч|м)\b)",
    re.IGNORECASE,
)

_GOOGLE_CABIN_CODE: dict[str, str] = {
    "economy": "1",
    "premium": "2",
    "business": "3",
    "first": "4",
}

_SOURCE_ALIASES = {
    "auto": "auto",
    "aviasales": "aviasales",
    "aviasales.ru": "aviasales",
    "google": "google_flights",
    "google flights": "google_flights",
    "google_flights": "google_flights",
}

_SOURCE_LABELS = {
    "aviasales": "Aviasales",
    "google_flights": "Google Flights",
}

_LOCATION_ALIASES = {
    "saint petersburg": "LED",
    "st petersburg": "LED",
    "st. petersburg": "LED",
    "petersburg": "LED",
    "spb": "LED",
    "piter": "LED",
    "sankt peterburg": "LED",
    "sanct petersburg": "LED",
    "санкт петербург": "LED",
    "санкт-петербург": "LED",
    "спб": "LED",
    "питер": "LED",
    "moscow": "MOW",
    "москва": "MOW",
    "dubai": "DXB",
    "дубай": "DXB",
    "istanbul": "IST",
    "стамбул": "IST",
    "london": "LON",
    "лондон": "LON",
    "paris": "PAR",
    "париж": "PAR",
    "rome": "ROM",
    "рим": "ROM",
    "new york": "NYC",
    "нью йорк": "NYC",
    "barcelona": "BCN",
    "барселона": "BCN",
    "tokyo": "TYO",
    "токио": "TYO",
    "antalya": "AYT",
    "анталья": "AYT",
    "almaty": "ALA",
    "алматы": "ALA",
    "tbilisi": "TBS",
    "тбилиси": "TBS",
    "yerevan": "EVN",
    "ереван": "EVN",
}


def _parse_date(raw: str) -> str:
    raw = raw.strip()
    lower = raw.lower()
    today = datetime.now()

    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    relative = {
        "today": today,
        "bugun": today,
        "bugün": today,
        "tomorrow": today + timedelta(days=1),
        "yarin": today + timedelta(days=1),
        "yarın": today + timedelta(days=1),
    }
    for key, val in relative.items():
        if key in lower:
            return val.strftime("%Y-%m-%d")

    try:
        client = _gemini_client()
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=(
                f"Today is {today.strftime('%Y-%m-%d')}. "
                f"Convert this date expression to YYYY-MM-DD: '{raw}'. "
                f"Return ONLY the date string, nothing else."
            ),
        )
        result = response.text.strip()
        if re.match(r"\d{4}-\d{2}-\d{2}", result):
            return result
    except Exception as e:
        print(f"[FlightFinder] ⚠️ Gemini date parse failed: {e}")

    for month_name, month_num in _MONTH_MAP.items():
        if month_name in lower:
            day_match = re.search(r"\d{1,2}", raw)
            if day_match:
                day = int(day_match.group())
                year = today.year if month_num >= today.month else today.year + 1
                return f"{year}-{month_num:02d}-{day:02d}"

    print(f"[FlightFinder] ⚠️ Could not parse date '{raw}' — using today.")
    return today.strftime("%Y-%m-%d")


def _normalize_source(raw: str) -> str:
    key = (raw or "auto").strip().lower()
    return _SOURCE_ALIASES.get(key, "auto")


def _int_param(
    params: dict,
    *names: str,
    default: int = 0,
    minimum: int = 0,
    maximum: int = 9,
) -> int:
    for name in names:
        if name not in params or params.get(name) in (None, ""):
            continue
        try:
            return max(minimum, min(maximum, int(params.get(name))))
        except (TypeError, ValueError):
            continue
    return max(minimum, min(maximum, default))


def _normalize_location_key(raw: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\sа-яА-ЯёЁ-]", " ", raw.lower())).strip()


def _extract_explicit_iata(raw: str) -> str | None:
    cleaned = raw.strip().upper()
    if _IATA_RE.fullmatch(cleaned):
        return cleaned

    bracketed = re.search(r"[\(\[]\s*([A-Z]{3})\s*[\)\]]", cleaned)
    if bracketed:
        return bracketed.group(1)

    tokens = _INLINE_IATA_RE.findall(cleaned)
    if tokens:
        return tokens[-1]
    return None


def _resolve_iata_code(raw: str, role: str) -> str | None:
    explicit = _extract_explicit_iata(raw)
    if explicit:
        return explicit

    alias = _LOCATION_ALIASES.get(_normalize_location_key(raw))
    if alias:
        return alias

    try:
        client = _gemini_client()
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=(
                "Resolve the following flight search input to a single IATA code.\n"
                f"Field: {role}\n"
                f"Input: {raw}\n"
                "Rules:\n"
                "- Return exactly one 3-letter uppercase IATA code.\n"
                "- Prefer the city IATA code when the input refers to a city or metro area.\n"
                "- Prefer the airport IATA code when the input clearly names a specific airport.\n"
                "- Return nothing except the code.\n"
            ),
        )
        result = response.text.strip().upper()
        if _IATA_RE.fullmatch(result):
            return result
    except Exception as e:
        print(f"[FlightFinder] ⚠️ Gemini IATA resolve failed for '{raw}': {e}")

    return None


def _build_google_flights_url(
    origin: str,
    destination: str,
    date: str,
    return_date: str | None = None,
    passengers: int = 1,
    cabin: str = "economy",
) -> str:
    base = "https://www.google.com/travel/flights"
    cabin_code = _GOOGLE_CABIN_CODE.get(cabin.lower(), "1")

    if return_date:
        trip = f"Flights from {origin} to {destination} on {date} returning {return_date}"
    else:
        trip = f"Flights from {origin} to {destination} on {date}"

    return base + "?" + urlencode({
        "q": trip,
        "hl": "en",
        "curr": "USD",
        "adults": str(passengers),
        "cabin": cabin_code,
    })


def _build_aviasales_url(
    origin_code: str,
    destination_code: str,
    date: str,
    return_date: str | None = None,
    passengers: int = 1,
    cabin: str = "economy",
    children: int = 0,
    infants: int = 0,
) -> str:
    depart = datetime.strptime(date, "%Y-%m-%d").strftime("%d%m")
    adults = max(1, min(9, int(passengers)))
    kids = max(0, min(9, int(children)))
    babies = max(0, min(9, int(infants)))

    slug = f"{origin_code.upper()}{depart}{destination_code.upper()}"
    if return_date:
        slug += datetime.strptime(return_date, "%Y-%m-%d").strftime("%d%m")

    if kids or babies:
        slug += f"{adults}{kids}{babies}"
    else:
        slug += str(adults)
    return f"https://www.aviasales.ru/search/{slug}"


def _looks_like_results(raw_text: str, source: str) -> bool:
    if not raw_text or len(raw_text) < 350:
        return False

    text = raw_text.lower()
    time_hits = len(_TIME_RE.findall(raw_text))
    price_hits = len(_PRICE_RE.findall(raw_text))
    if time_hits >= 2 and price_hits >= 1:
        return True
    if time_hits >= 2 and _STOP_RE.search(raw_text) and _DURATION_RE.search(raw_text):
        return True

    keyword_groups = {
        "aviasales": (
            "авиабилеты", "билеты", "пересад", "багаж", "купить", "выбрать",
            "ticket", "stops", "baggage", "flight",
        ),
        "google_flights": (
            "departing", "arriving", "best", "cheapest", "flights", "stops",
            "price", "duration",
        ),
    }

    hits = sum(1 for word in keyword_groups.get(source, ()) if word in text)
    return hits >= 2 or len(raw_text) > 2200


def _decode_browser_blocks(raw: str) -> list[str]:
    if not isinstance(raw, str) or not raw or raw.startswith("Could not extract flight blocks"):
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []

    blocks: list[str] = []
    for item in data:
        if not isinstance(item, str):
            continue
        cleaned = re.sub(r"\n{3,}", "\n\n", item.strip())
        if cleaned:
            blocks.append(cleaned)
    return blocks


def _blocks_look_useful(blocks: list[str]) -> bool:
    if not blocks:
        return False
    joined = "\n".join(blocks)
    return (
        len(blocks) >= 2
        or (len(_TIME_RE.findall(joined)) >= 2 and len(_PRICE_RE.findall(joined)) >= 1)
        or (_STOP_RE.search(joined) is not None and _DURATION_RE.search(joined) is not None)
    )


def _compose_result_text(page_text: str, blocks: list[str], source: str) -> str:
    sections: list[str] = []

    if blocks:
        sections.append(f"{_SOURCE_LABELS.get(source, source)} extracted flight cards:")
        for index, block in enumerate(blocks[:8], 1):
            sections.append(f"[Card {index}]\n{block[:1800]}")

    if page_text:
        if blocks:
            sections.append(f"Page text snapshot:\n{page_text[:4000]}")
        else:
            sections.append(page_text[:12000])

    merged = "\n\n".join(part.strip() for part in sections if part and part.strip())
    return merged[:14_000]


def _search_flights_browser(url: str, source: str) -> tuple[str, str]:
    from actions.browser_control import browser_control

    print(f"[FlightFinder] 🌐 Opening {_SOURCE_LABELS.get(source, source)}: {url}")
    browser_control({"action": "go_to", "url": url})

    best_page_text = ""
    best_blocks: list[str] = []
    best_combined_text = ""
    best_url = url

    for attempt in range(1, 9):
        time.sleep(5 if attempt == 1 else 2.5)

        current_url = browser_control({"action": "get_url"})
        if isinstance(current_url, str) and current_url and not current_url.startswith("Could"):
            best_url = current_url

        block_payload = browser_control({
            "action": "extract_flight_blocks",
            "provider": source,
            "max_items": 8,
            "max_chars": 1800,
        })
        blocks = _decode_browser_blocks(block_payload)
        if sum(len(block) for block in blocks) > sum(len(block) for block in best_blocks):
            best_blocks = blocks

        raw = browser_control({"action": "get_text", "max_chars": 12000})
        if isinstance(raw, str) and raw and not raw.startswith("Could not get page text"):
            if len(raw) > len(best_page_text):
                best_page_text = raw

        combined = _compose_result_text(best_page_text, best_blocks, source)
        if len(combined) > len(best_combined_text):
            best_combined_text = combined

        if _blocks_look_useful(best_blocks) or _looks_like_results(best_combined_text, source):
            break

        if attempt in (2, 4, 6, 7):
            browser_control({"action": "scroll", "direction": "down", "amount": 1200})

    return best_combined_text.strip(), best_url


def _parse_flights_with_gemini(
    raw_text: str,
    origin: str,
    destination: str,
    date: str,
    source: str,
) -> list[dict]:
    prompt = (
        "You extract flight options from raw flight-search page text. "
        "Return ONLY valid JSON. No markdown. No explanation.\n\n"
        f"Source: {_SOURCE_LABELS.get(source, source)}\n"
        f"Route: {origin} -> {destination}\n"
        f"Departure date: {date}\n\n"
        "Extract up to 10 concrete flight options from the raw page text below.\n"
        "Use this JSON schema exactly:\n"
        '[{"airline":"...","departure":"HH:MM","arrival":"HH:MM",'
        '"duration":"Xh Ym","stops":0,"price":"12345","currency":"RUB"}]\n'
        "Rules:\n"
        "- Prioritize the cheapest visible ticket/result cards, not the page's marketing blocks.\n"
        "- Include the lowest-priced visible option even if it is not listed first on the page.\n"
        "- Ignore baggage weights, CO2/emissions numbers, filter chips, date-grid prices, and ads.\n"
        "- stops must be an integer.\n"
        "- price should contain digits only if possible.\n"
        "- currency should be a short code like RUB, USD, EUR.\n"
        "- If the page does not contain reliable flight results, return [].\n\n"
        f"RAW PAGE TEXT:\n{raw_text[:12000]}"
    )

    try:
        client = _gemini_client()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        text = re.sub(r"```(?:json)?", "", response.text).strip().rstrip("`").strip()
        flights = json.loads(text)
        return flights if isinstance(flights, list) else []
    except Exception as e:
        print(f"[FlightFinder] ⚠️ Gemini parse failed: {e}")
        return []


def _price_value(flight: dict) -> int | None:
    raw_price = str(flight.get("price", "")).strip()
    if not raw_price:
        return None

    digits = re.sub(r"[^\d]", "", raw_price)
    if not digits:
        return None

    try:
        return int(digits)
    except ValueError:
        return None


def _sort_flights_by_price(flights: list[dict]) -> list[dict]:
    return sorted(
        flights,
        key=lambda flight: (
            _price_value(flight) is None,
            _price_value(flight) or 999_999_999,
        ),
    )


def _stop_text(stops: object) -> str:
    try:
        stops_num = int(stops)
    except Exception:
        stops_num = 0
    return "non-stop" if stops_num == 0 else f"{stops_num} stop{'s' if stops_num > 1 else ''}"


def _format_spoken(
    flights: list[dict],
    origin: str,
    destination: str,
    date: str,
    source: str,
) -> str:
    if not flights:
        return (
            f"I opened {_SOURCE_LABELS.get(source, source)} for flights from "
            f"{origin} to {destination} on {date}, sir, but could not extract "
            "reliable options from the page."
        )

    ordered_flights = _sort_flights_by_price(flights)
    cheapest = next((flight for flight in ordered_flights if _price_value(flight) is not None), None)

    if cheapest:
        cheapest_price = f"{cheapest.get('price', 'N/A')} {cheapest.get('currency', '')}".strip()
        lines = [
            f"The cheapest flight I found from {origin} to {destination} on {date} is "
            f"{cheapest.get('airline', 'an unknown airline')} at {cheapest_price}, "
            f"departing {cheapest.get('departure', '--:--')}, {_stop_text(cheapest.get('stops', 0))}."
        ]
    else:
        lines = [f"Here are the parsed flights from {origin} to {destination} on {date}, sir."]

    for i, flight in enumerate(ordered_flights[:5], 1):
        airline = flight.get("airline", "Unknown airline")
        departure = flight.get("departure", "--:--")
        arrival = flight.get("arrival", "--:--")
        duration = flight.get("duration", "")
        stops = flight.get("stops", 0)
        price = flight.get("price", "")
        currency = flight.get("currency", "")

        price_str = f"{price} {currency}".strip() if price else "price unavailable"
        dur_str = f", {duration}" if duration else ""

        lines.append(
            f"Option {i}: {airline}, departing {departure}, "
            f"arriving {arrival}{dur_str}, {_stop_text(stops)}, {price_str}."
        )

    return " ".join(lines)


def _format_text_report(
    flights: list[dict],
    origin: str,
    destination: str,
    date: str,
    return_date: str | None,
    page_url: str,
    source: str,
    resolved_origin: str | None,
    resolved_destination: str | None,
) -> str:
    lines = [
        "JARVIS - Flight Search Results",
        "-" * 50,
        f"Source    : {_SOURCE_LABELS.get(source, source)}",
        f"Route     : {origin} -> {destination}",
        f"Date      : {date}",
    ]
    if resolved_origin and resolved_destination:
        lines.append(f"IATA      : {resolved_origin} -> {resolved_destination}")
    if return_date:
        lines.append(f"Return    : {return_date}")
    lines += [
        f"Searched  : {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Page URL  : {page_url}",
        "-" * 50,
        "",
    ]

    if not flights:
        lines.append("No reliable flights could be extracted from the page.")
    else:
        for i, flight in enumerate(_sort_flights_by_price(flights), 1):
            stop_str = _stop_text(flight.get("stops", 0)).replace("non-stop", "Non-stop")
            lines += [
                f"Flight {i}:",
                f"  Airline   : {flight.get('airline', 'N/A')}",
                f"  Departure : {flight.get('departure', 'N/A')}",
                f"  Arrival   : {flight.get('arrival', 'N/A')}",
                f"  Duration  : {flight.get('duration', 'N/A')}",
                f"  Stops     : {stop_str}",
                f"  Price     : {flight.get('price', 'N/A')} {flight.get('currency', '')}",
                "",
            ]

    return "\n".join(lines)


def _save_to_desktop(content: str, origin: str, destination: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"flights_{origin}_{destination}_{ts}.txt".replace(" ", "_")
    desktop = Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    filepath = desktop / filename

    filepath.write_text(content, encoding="utf-8")
    print(f"[FlightFinder] 💾 Saved: {filepath}")

    try:
        if is_windows():
            subprocess.Popen(["notepad.exe", str(filepath)])
        elif is_mac():
            subprocess.Popen(["open", "-t", str(filepath)])
        elif is_linux():
            subprocess.Popen(["xdg-open", str(filepath)])
    except Exception as e:
        print(f"[FlightFinder] ⚠️ Could not open text editor: {e}")

    return str(filepath)


def _build_search_attempts(
    source: str,
    origin: str,
    destination: str,
    date: str,
    return_date: str | None,
    adults: int,
    children: int,
    infants: int,
    cabin: str,
) -> tuple[list[dict], str | None, str | None]:
    attempts: list[dict] = []
    origin_code = None
    destination_code = None

    if source in {"auto", "aviasales"}:
        origin_code = _resolve_iata_code(origin, "origin")
        destination_code = _resolve_iata_code(destination, "destination")

        if origin_code and destination_code:
            attempts.append({
                "source": "aviasales",
                "url": _build_aviasales_url(
                    origin_code,
                    destination_code,
                    date,
                    return_date,
                    adults,
                    cabin,
                    children,
                    infants,
                ),
            })
        else:
            print(
                f"[FlightFinder] ⚠️ Could not resolve IATA codes "
                f"({origin!r} -> {origin_code}, {destination!r} -> {destination_code})"
            )

    if source in {"auto", "aviasales", "google_flights"}:
        attempts.append({
            "source": "google_flights",
            "url": _build_google_flights_url(
                origin,
                destination,
                date,
                return_date,
                adults,
                cabin,
            ),
        })

    return attempts, origin_code, destination_code


def flight_finder(parameters: dict, player=None, speak=None) -> str:
    params = parameters or {}

    origin = params.get("origin", "").strip()
    destination = params.get("destination", "").strip()
    date_raw = params.get("date", "").strip()
    return_raw = (params.get("return_date") or "").strip()
    adults = _int_param(params, "adults", "passengers", default=1, minimum=1, maximum=9)
    children = _int_param(params, "children", "child", "kids", default=0, minimum=0, maximum=9)
    infants = _int_param(params, "infants", "infant", "babies", default=0, minimum=0, maximum=9)
    cabin = params.get("cabin", "economy").strip().lower()
    save = bool(params.get("save", False))
    source = _normalize_source(params.get("source", "auto"))

    if not origin or not destination:
        return "Please provide both origin and destination, sir."
    if not date_raw:
        return "Please provide a departure date, sir."

    if cabin not in _GOOGLE_CABIN_CODE:
        cabin = "economy"

    date = _parse_date(date_raw)
    return_date = _parse_date(return_raw) if return_raw else None

    if player:
        player.write_log(f"[FlightFinder] {origin} -> {destination} on {date}")

    if speak:
        speak(f"Searching flights from {origin} to {destination} on {date}, sir.")

    print(
        f"[FlightFinder] ▶️ {origin} -> {destination} | {date}"
        f"{' -> ' + return_date if return_date else ''}"
        f" | {cabin} | adults={adults}, children={children}, infants={infants}"
        f" | source={source}"
    )

    attempts, origin_code, destination_code = _build_search_attempts(
        source,
        origin,
        destination,
        date,
        return_date,
        adults,
        children,
        infants,
        cabin,
    )

    if not attempts:
        return "Could not build a valid flight search, sir."

    last_raw_text = ""
    last_page_url = ""
    last_source = attempts[0]["source"]
    flights: list[dict] = []

    try:
        for attempt in attempts:
            source_name = attempt["source"]
            raw_text, page_url = _search_flights_browser(attempt["url"], source_name)

            if raw_text and len(raw_text) > len(last_raw_text):
                last_raw_text = raw_text
                last_page_url = page_url
                last_source = source_name

            if not raw_text:
                print(f"[FlightFinder] ⚠️ Empty page text from {source_name}")
                continue

            if speak:
                speak("Analysing the results now, sir.")

            parsed = _parse_flights_with_gemini(raw_text, origin, destination, date, source_name)
            if parsed:
                flights = parsed
                last_raw_text = raw_text
                last_page_url = page_url
                last_source = source_name
                break

            print(f"[FlightFinder] ⚠️ No structured flights extracted from {source_name}")

        if not last_raw_text:
            return "Could not retrieve flight data, sir. The page may not have loaded."

        spoken = _format_spoken(flights, origin, destination, date, last_source)

        if speak:
            speak(spoken)

        result = spoken

        if save:
            report = _format_text_report(
                flights,
                origin,
                destination,
                date,
                return_date,
                last_page_url,
                last_source,
                origin_code,
                destination_code,
            )
            saved_path = _save_to_desktop(report, origin, destination)
            result += f" Results saved to Desktop: {saved_path}"

        return result

    except Exception as e:
        print(f"[FlightFinder] ❌ {e}")
        return f"Flight search failed, sir: {e}"
