from urllib.parse import parse_qs, urlparse

from actions.flight_finder import (
    _blocks_look_useful,
    _build_aviasales_url,
    _build_search_attempts,
    _compose_result_text,
    _build_google_flights_url,
    _decode_browser_blocks,
    _extract_explicit_iata,
    _looks_like_results,
    _normalize_location_key,
    _normalize_source,
    _looks_like_loading,
    _looks_like_no_results,
    _parse_aviasales_text,
    _price_value,
    _resolve_iata_code,
    _sanitize_flights,
    _sort_flights_by_price,
    _format_spoken,
)


def test_build_aviasales_one_way_url():
    url = _build_aviasales_url("LED", "DXB", "2026-06-16", passengers=2, cabin="business")

    assert url == "https://www.aviasales.ru/search/LED1606DXB2"


def test_build_aviasales_one_way_economy_slug_url():
    url = _build_aviasales_url("LED", "DXB", "2026-06-16", passengers=1, cabin="economy")

    assert url == "https://www.aviasales.ru/search/LED1606DXB1"


def test_build_aviasales_round_trip_url_has_return_segment():
    url = _build_aviasales_url(
        "LED",
        "MAD",
        "2026-06-19",
        return_date="2026-06-26",
        passengers=2,
        cabin="economy",
        children=1,
        infants=1,
    )

    assert url == "https://www.aviasales.ru/search/LED1906MAD2606211"


def test_build_aviasales_includes_zero_when_infant_without_child():
    url = _build_aviasales_url(
        "LED",
        "MAD",
        "2026-06-19",
        passengers=2,
        infants=1,
    )

    assert url == "https://www.aviasales.ru/search/LED1906MAD201"


def test_build_google_flights_url_is_query_based():
    url = _build_google_flights_url("Saint Petersburg", "Dubai", "2026-06-16", passengers=1)
    parsed = parse_qs(urlparse(url).query)

    assert url.startswith("https://www.google.com/travel/flights?")
    assert "tfs" not in parsed
    assert parsed["adults"] == ["1"]
    assert "Saint Petersburg" in parsed["q"][0]
    assert "Dubai" in parsed["q"][0]


def test_extract_explicit_iata_from_plain_code_and_embedded_text():
    assert _extract_explicit_iata("LED") == "LED"
    assert _extract_explicit_iata("Saint Petersburg (LED)") == "LED"
    assert _extract_explicit_iata("fly from dxb") == "DXB"


def test_normalize_source_aliases():
    assert _normalize_source("aviasales.ru") == "aviasales"
    assert _normalize_source("google") == "aviasales"
    assert _normalize_source("something-else") == "aviasales"


def test_normalize_location_key_preserves_lookup_shape():
    assert _normalize_location_key("Санкт-Петербург") == "санкт-петербург"
    assert _normalize_location_key("Saint   Petersburg") == "saint petersburg"


def test_tenerife_defaults_to_north_unless_south_is_explicit():
    assert _resolve_iata_code("Тенерифе", "destination") == "TFN"
    assert _resolve_iata_code("Tenerife", "destination") == "TFN"
    assert _resolve_iata_code("Тенерифе южный", "destination") == "TFS"


def test_search_attempts_only_use_aviasales():
    attempts, origin_code, destination_code = _build_search_attempts(
        "aviasales",
        "LED",
        "Тенерифе",
        "2026-06-19",
        None,
        1,
        0,
        0,
        "economy",
    )

    assert origin_code == "LED"
    assert destination_code == "TFN"
    assert [attempt["source"] for attempt in attempts] == ["aviasales"]
    assert attempts[0]["url"] == "https://www.aviasales.ru/search/LED1906TFN1"


def test_decode_browser_blocks_and_compose_result_text():
    raw = '["Turkish Airlines\\n10:35 15:10\\n3 ч 35 м\\nБез пересадок\\n12 345 ₽"]'
    blocks = _decode_browser_blocks(raw)

    assert blocks == ["Turkish Airlines\n10:35 15:10\n3 ч 35 м\nБез пересадок\n12 345 ₽"]

    merged = _compose_result_text("Header text only", blocks, "aviasales")
    assert "Aviasales extracted flight cards:" in merged
    assert "[Card 1]" in merged
    assert "12 345 ₽" in merged


def test_result_heuristics_detect_flight_card_like_text():
    block = "Turkish Airlines\n10:35 15:10\n3 ч 35 м\nБез пересадок\n12 345 ₽"

    assert _blocks_look_useful([block]) is True
    assert _looks_like_results(block * 10, "aviasales") is True


def test_result_heuristics_ignore_aviasales_calendar_grid():
    grid = ("22-29 Jun\nFind\n23-30 Jun\nFind\n24 Jun - 1 Jul\nFind\n" * 100)

    assert _blocks_look_useful([grid]) is False
    assert _looks_like_results(grid, "aviasales") is False


def test_aviasales_status_heuristics_detect_loading_and_no_results():
    assert _looks_like_loading("Ищем билеты, пожалуйста подождите") is True
    assert _looks_like_no_results("Мы не нашли билетов по этому направлению") is True


def test_price_value_handles_human_formatted_prices():
    assert _price_value({"price": "10 561"}) == 10561
    assert _price_value({"price": "1,828"}) == 1828
    assert _price_value({"price": "price unavailable"}) is None


def test_sanitize_flights_drops_bad_price_and_fills_airline():
    flights = _sanitize_flights([
        {"airline": "", "departure": "--:--", "arrival": "--:--", "price": "9"},
        {"airline": "", "departure": "10:35", "arrival": "15:10", "price": "64 753", "currency": "RUB"},
    ])

    assert len(flights) == 1
    assert flights[0]["airline"] == "Unknown airline"
    assert flights[0]["price"] == "64 753"


def test_parse_aviasales_text_extracts_visible_ticket_list():
    raw = """
    Цены на соседние даты
    19 июл
    36 263 ₽
    20 июл
    30 441 ₽
    Сохранить поиск
    Самый быстрый
    41 937 ₽
    Оптимальный
    Багаж 30 кг
    Ручная кладь 8 кг
    01:40
    Санкт-Петербург
    LED
    9 ч 45 м в пути, 1 пересадка
    IST
    MAD
    10:25
    Мадрид
    Самый дешёвый
    30 441 ₽
    Багаж 20 кг
    Ручная кладь 8 кг
    15:00
    Санкт-Петербург
    LED
    1 д 2 ч в пути, 1 пересадка
    SAW
    MAD
    16:00
    Мадрид
    30 906 ₽
    Багаж 20 кг
    Ручная кладь
    15:00
    Санкт-Петербург
    LED
    23 ч 30 м в пути, 1 пересадка
    SAW
    MAD
    13:30
    Мадрид
    32 816 ₽
    46 722 ₽ с багажом
    Без ручной клади
    21:50
    Санкт-Петербург
    LED
    1 д 12 ч 20 м в пути, 3 пересадки
    SVO
    EVN
    MXP
    MAD
    09:10
    Мадрид
    Показать ещё билеты
    Авиакомпании
    """

    flights = _parse_aviasales_text(raw)

    assert [flight["price"] for flight in flights] == ["41 937 ₽", "30 441 ₽", "30 906 ₽", "32 816 ₽"]
    assert flights[0]["duration"] == "9 ч 45 м"
    assert flights[1]["stops"] == 1
    assert flights[3]["stops"] == 3
    assert flights[3]["departure"] == "21:50"
    assert flights[3]["arrival"] == "09:10"


def test_sort_flights_by_price_places_cheapest_first():
    flights = [
        {"airline": "Direct", "price": "11 179"},
        {"airline": "Transfer", "price": "10 561"},
        {"airline": "Unknown"},
    ]

    sorted_flights = _sort_flights_by_price(flights)

    assert [flight.get("airline") for flight in sorted_flights] == [
        "Transfer",
        "Direct",
        "Unknown",
    ]


def test_format_spoken_leads_with_cheapest_parsed_flight():
    flights = [
        {
            "airline": "Direct Air",
            "departure": "09:50",
            "arrival": "14:40",
            "duration": "3h 50m",
            "stops": 0,
            "price": "11 179",
            "currency": "RUB",
        },
        {
            "airline": "Transfer Air",
            "departure": "13:05",
            "arrival": "22:10",
            "duration": "8h 5m",
            "stops": 1,
            "price": "10 561",
            "currency": "RUB",
        },
    ]

    spoken = _format_spoken(flights, "St. Petersburg", "Yerevan", "2026-05-16", "aviasales")

    assert spoken.startswith(
        "The cheapest flight I found from St. Petersburg to Yerevan on 2026-05-16 "
        "is Transfer Air at 10 561 RUB"
    )
    assert "Option 1: Transfer Air" in spoken


def test_format_spoken_no_flights_keeps_open_page_url():
    spoken = _format_spoken(
        [],
        "Петербург",
        "Мадрид",
        "2026-08-05",
        "aviasales",
        "https://www.aviasales.ru/search/LED0508MAD12081",
    )

    assert "could not extract reliable options" in spoken
    assert "https://www.aviasales.ru/search/LED0508MAD12081" in spoken
