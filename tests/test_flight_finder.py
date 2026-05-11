from urllib.parse import parse_qs, urlparse

from actions.flight_finder import (
    _blocks_look_useful,
    _build_aviasales_url,
    _compose_result_text,
    _build_google_flights_url,
    _decode_browser_blocks,
    _extract_explicit_iata,
    _looks_like_results,
    _normalize_location_key,
    _normalize_source,
    _price_value,
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
    assert _normalize_source("google") == "google_flights"
    assert _normalize_source("something-else") == "auto"


def test_normalize_location_key_preserves_lookup_shape():
    assert _normalize_location_key("Санкт-Петербург") == "санкт-петербург"
    assert _normalize_location_key("Saint   Petersburg") == "saint petersburg"


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


def test_price_value_handles_human_formatted_prices():
    assert _price_value({"price": "10 561"}) == 10561
    assert _price_value({"price": "1,828"}) == 1828
    assert _price_value({"price": "price unavailable"}) is None


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
