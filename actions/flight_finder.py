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
from core.interrupts import is_interrupted


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
_NO_RESULTS_RE = re.compile(
    r"нет\s+(?:билетов|рейсов|вариантов)|не\s+нашли|ничего\s+не\s+найдено|"
    r"no\s+(?:flights|tickets|results)|nothing\s+found",
    re.IGNORECASE,
)
_LOADING_RE = re.compile(
    r"ищем|загруз|подожд|loading|searching|please\s+wait",
    re.IGNORECASE,
)
_AVIASALES_MORE_TEXT = "Показать ещё билеты"
_AVIASALES_SECTION_END_RE = re.compile(
    r"^(?:показать ещё билеты|авиакомпании|направления|города|аэропорты|авиасейлс в мире|помощь и советы)$",
    re.IGNORECASE,
)
_AVIASALES_LABEL_RE = re.compile(
    r"(?:самый|оптимальн|быстр|деш[её]в|удобн|лучш)",
    re.IGNORECASE,
)
_BROWSER_SEARCH_MAX_ATTEMPTS = 7
_BROWSER_SEARCH_INITIAL_DELAY_SECONDS = 2.0
_BROWSER_SEARCH_POLL_DELAY_SECONDS = 1.25
_BROWSER_SEARCH_CLICK_DELAY_SECONDS = 1.5
_BROWSER_SEARCH_RELOAD_DELAY_SECONDS = 2.0
_BROWSER_SEARCH_LOAD_MORE_DELAY_SECONDS = 1.5
_AVIASALES_EARLY_ENOUGH_RESULTS = 3

_GOOGLE_CABIN_CODE: dict[str, str] = {
    "economy": "1",
    "premium": "2",
    "business": "3",
    "first": "4",
}

_SOURCE_ALIASES = {
    "auto": "aviasales",
    "aviasales": "aviasales",
    "aviasales.ru": "aviasales",
    "google": "aviasales",
    "google flights": "aviasales",
    "google_flights": "aviasales",
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
    "brussels": "BRU",
    "bruxelles": "BRU",
    "brussel": "BRU",
    "брюссель": "BRU",
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
    "tenerife": "TFN",
    "tenerife island": "TFN",
    "tenerife north": "TFN",
    "tenerife norte": "TFN",
    "tenerife north airport": "TFN",
    "tenerife south": "TFS",
    "tenerife sur": "TFS",
    "tenerife south airport": "TFS",
    "тенерифе": "TFN",
    "остров тенерифе": "TFN",
    "тенерифе северный": "TFN",
    "тенерифе север": "TFN",
    "аэропорт тенерифе северный": "TFN",
    "тенерифе южный": "TFS",
    "тенерифе юг": "TFS",
    "аэропорт тенерифе южный": "TFS",
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
    return _SOURCE_ALIASES.get(key, "aviasales")


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
    if source == "aviasales":
        return False

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
        (len(_TIME_RE.findall(joined)) >= 2 and len(_PRICE_RE.findall(joined)) >= 1)
        or (_STOP_RE.search(joined) is not None and _DURATION_RE.search(joined) is not None)
    )


def _normalize_aviasales_text(raw_text: str) -> list[str]:
    text = (raw_text or "").replace("\u2060", "")
    text = re.sub(r"[\u00a0\u202f\u2009\u200a\u200b]+", " ", text)
    return [
        re.sub(r"\s+", " ", line).strip()
        for line in text.splitlines()
        if re.sub(r"\s+", " ", line).strip()
    ]


def _line_price(line: str) -> str | None:
    match = re.search(r"\d[\d\s.,]{2,}\s*(?:₽|руб\.?|RUB)", line, re.IGNORECASE)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group()).strip()


def _line_is_baggage_price(line: str) -> bool:
    return bool(re.search(r"с\s+багажом|baggage", line, re.IGNORECASE))


def _line_is_ticket_price_start(lines: list[str], index: int) -> bool:
    line = lines[index]
    if not _line_price(line) or _line_is_baggage_price(line):
        return False
    window = "\n".join(lines[index + 1:index + 16])
    return bool(_TIME_RE.search(window) and re.search(r"\b[A-Z]{3}\b", window) and "в пути" in window.lower())


def _parse_stops(text: str) -> int:
    if re.search(r"без\s+пересад|direct|non-stop|nonstop", text, re.IGNORECASE):
        return 0
    match = re.search(r"(\d+)\s+пересад", text, re.IGNORECASE)
    return int(match.group(1)) if match else 0


def _parse_duration(text: str) -> str:
    match = re.search(r"((?:\d+\s*д\s*)?(?:\d+\s*ч\s*)?(?:\d+\s*м\s*)?)\s*в пути", text, re.IGNORECASE)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def _parse_aviasales_text(raw_text: str) -> list[dict]:
    lines = _normalize_aviasales_text(raw_text)
    if not lines:
        return []

    start = 0
    for index, line in enumerate(lines):
        if line.lower() == "сохранить поиск":
            start = index + 1
            break

    end = len(lines)
    for index in range(start, len(lines)):
        if _AVIASALES_SECTION_END_RE.match(lines[index]):
            end = index
            break

    section = lines[start:end]
    starts = [
        index for index in range(len(section))
        if _line_is_ticket_price_start(section, index)
    ]
    flights: list[dict] = []

    for position, price_index in enumerate(starts):
        next_index = starts[position + 1] if position + 1 < len(starts) else len(section)
        block = section[price_index:next_index]
        block_text = "\n".join(block)

        times = _TIME_RE.findall(block_text)
        if len(times) < 2:
            continue

        label = ""
        for offset in (1, 2):
            candidate_index = price_index - offset
            if candidate_index >= 0 and _AVIASALES_LABEL_RE.search(section[candidate_index]):
                label = section[candidate_index]
                break

        price = _line_price(section[price_index]) or ""
        baggage = "; ".join(
            line for line in block
            if re.search(r"багаж|ручная кладь|небольшая сумка|без ручной", line, re.IGNORECASE)
            and not _line_is_baggage_price(line)
        )

        flights.append({
            "airline": label or "Unknown airline",
            "departure": times[0],
            "arrival": times[-1],
            "duration": _parse_duration(block_text),
            "stops": _parse_stops(block_text),
            "price": price,
            "currency": "RUB" if "₽" in price or "руб" in price.lower() else "",
            "baggage": baggage,
        })

    return _sanitize_flights(flights)


def _looks_like_no_results(raw_text: str) -> bool:
    return bool(raw_text and _NO_RESULTS_RE.search(raw_text))


def _looks_like_loading(raw_text: str) -> bool:
    return bool(raw_text and _LOADING_RE.search(raw_text))


def _compose_result_text(page_text: str, blocks: list[str], source: str) -> str:
    sections: list[str] = []

    if blocks:
        sections.append(f"{_SOURCE_LABELS.get(source, source)} extracted flight cards:")
        for index, block in enumerate(blocks[:20], 1):
            sections.append(f"[Card {index}]\n{block[:3000]}")

    if page_text:
        if blocks:
            snapshot_limit = 12_000 if source == "aviasales" else 4_000
            sections.append(f"Page text snapshot:\n{page_text[:snapshot_limit]}")
        else:
            sections.append(page_text[:12000])

    merged = "\n\n".join(part.strip() for part in sections if part and part.strip())
    return merged[:14_000]


def _search_wait_seconds(attempt: int) -> float:
    return (
        _BROWSER_SEARCH_INITIAL_DELAY_SECONDS
        if attempt <= 1
        else _BROWSER_SEARCH_POLL_DELAY_SECONDS
    )


def _should_capture_full_page_text(
    source: str,
    attempt: int,
    blocks: list[str],
    best_page_text: str,
) -> bool:
    if source != "aviasales":
        return True
    if attempt <= 2 or not best_page_text:
        return True
    if not blocks or not _blocks_look_useful(blocks):
        return True
    return attempt % 3 == 0


def _should_finish_aviasales_search(parsed_count: int, attempt: int, combined_text: str) -> bool:
    if parsed_count <= 0:
        return False
    if _looks_like_loading(combined_text):
        return False
    if parsed_count >= _AVIASALES_EARLY_ENOUGH_RESULTS:
        return True
    return attempt >= 3


def _search_flights_browser(url: str, source: str) -> tuple[str, str]:
    from actions.browser_control import browser_control

    print(f"[FlightFinder] 🌐 Opening {_SOURCE_LABELS.get(source, source)}: {url}")
    browser_control({"action": "go_to", "url": url})

    best_page_text = ""
    best_blocks: list[str] = []
    best_combined_text = ""
    best_url = url
    clicked_more_count = 0

    for attempt in range(1, _BROWSER_SEARCH_MAX_ATTEMPTS + 1):
        if is_interrupted():
            print("[FlightFinder] Stop requested; aborting browser search.")
            break

        time.sleep(_search_wait_seconds(attempt))

        current_url = browser_control({"action": "get_url"})
        if isinstance(current_url, str) and current_url and not current_url.startswith("Could"):
            best_url = current_url

        block_payload = browser_control({
            "action": "extract_flight_blocks",
            "provider": source,
            "max_items": 12,
            "max_chars": 2200,
        })
        blocks = _decode_browser_blocks(block_payload)
        if sum(len(block) for block in blocks) > sum(len(block) for block in best_blocks):
            best_blocks = blocks

        if _should_capture_full_page_text(source, attempt, best_blocks, best_page_text):
            raw = browser_control({"action": "get_text", "max_chars": 7000})
            if isinstance(raw, str) and raw and not raw.startswith("Could not get page text"):
                if len(raw) > len(best_page_text):
                    best_page_text = raw

        combined = _compose_result_text(best_page_text, best_blocks, source)
        if len(combined) > len(best_combined_text):
            best_combined_text = combined

        if _blocks_look_useful(best_blocks) or _looks_like_results(best_combined_text, source):
            if source != "aviasales":
                break
            parsed_count = len(_parse_aviasales_text(best_combined_text))
            if _should_finish_aviasales_search(parsed_count, attempt, best_combined_text):
                break
            if (
                parsed_count < _AVIASALES_EARLY_ENOUGH_RESULTS
                and clicked_more_count < 2
                and _AVIASALES_MORE_TEXT.lower() in best_combined_text.lower()
            ):
                clicked = browser_control({"action": "smart_click", "description": _AVIASALES_MORE_TEXT})
                if isinstance(clicked, str) and clicked.startswith("Clicked"):
                    clicked_more_count += 1
                    print(f"[FlightFinder] Loaded more Aviasales tickets ({clicked_more_count}).")
                    time.sleep(_BROWSER_SEARCH_LOAD_MORE_DELAY_SECONDS)
                    continue

        if _looks_like_no_results(best_combined_text):
            print("[FlightFinder] Aviasales reports no visible results.")
            break

        if source == "aviasales" and attempt in (2, 4):
            for label in ("Найти", "Искать", "Показать билеты", "Search", "Find tickets"):
                clicked = browser_control({"action": "smart_click", "description": label})
                if isinstance(clicked, str) and clicked.startswith("Clicked"):
                    print(f"[FlightFinder] Triggered Aviasales search button: {label}")
                    time.sleep(_BROWSER_SEARCH_CLICK_DELAY_SECONDS)
                    break

        if source == "aviasales" and attempt in (3, 5) and _looks_like_loading(best_combined_text):
            browser_control({"action": "reload"})
            time.sleep(_BROWSER_SEARCH_RELOAD_DELAY_SECONDS)

        if attempt in (2, 4, 6):
            browser_control({"action": "scroll", "direction": "down", "amount": 1200})

    return best_combined_text.strip(), best_url


def _parse_flights_with_gemini(
    raw_text: str,
    origin: str,
    destination: str,
    date: str,
    source: str,
) -> list[dict]:
    if source == "aviasales":
        parsed = _parse_aviasales_text(raw_text)
        if parsed:
            print(f"[FlightFinder] Parsed {len(parsed)} Aviasales tickets from page text.")
            return parsed

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
        return _sanitize_flights(flights) if isinstance(flights, list) else []
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


def _sanitize_flights(flights: list[dict]) -> list[dict]:
    cleaned: list[dict] = []
    for raw in flights:
        if not isinstance(raw, dict):
            continue

        flight = dict(raw)
        price = _price_value(flight)
        if price is not None and price < 100:
            flight["price"] = ""
            price = None

        airline = str(flight.get("airline") or "").strip()
        flight["airline"] = airline or "Unknown airline"

        departure = str(flight.get("departure") or "").strip()
        arrival = str(flight.get("arrival") or "").strip()
        has_times = bool(_TIME_RE.fullmatch(departure) or _TIME_RE.fullmatch(arrival))

        if price is None and not has_times:
            continue

        cleaned.append(flight)

    return cleaned


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
    page_url: str | None = None,
) -> str:
    if not flights:
        message = (
            f"I opened {_SOURCE_LABELS.get(source, source)} for flights from "
            f"{origin} to {destination} on {date}, sir, but could not extract "
            "reliable options from the page."
        )
        if page_url:
            message += f" The search page is open here: {page_url}"
        return message

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

    if source == "aviasales":
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
            if is_interrupted():
                return "Flight search cancelled."

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

        spoken = _format_spoken(flights, origin, destination, date, last_source, last_page_url)

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
