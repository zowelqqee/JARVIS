from core.interrupts import clear_interrupt, is_interrupted, is_stop_phrase, request_interrupt


def test_stop_phrase_accepts_russian_and_wake_word_variants():
    assert is_stop_phrase("стоп")
    assert is_stop_phrase("Джарвис, стоп")
    assert is_stop_phrase("Jarvis stop")


def test_stop_phrase_rejects_non_stop_text():
    assert not is_stop_phrase("стопка книг")
    assert not is_stop_phrase("Jarvis open settings")


def test_interrupt_flag_roundtrip():
    clear_interrupt()
    assert not is_interrupted()
    request_interrupt("test")
    assert is_interrupted()
    clear_interrupt()
    assert not is_interrupted()
