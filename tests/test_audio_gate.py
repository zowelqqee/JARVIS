from audio_gate import AudioTurnGate


def test_audio_gate_blocks_mic_during_output_and_short_tail():
    gate = AudioTurnGate(reopen_grace_seconds=0.35, drain_grace_seconds=0.45)

    gate.note_output_audio(now=10.0)

    assert gate.mic_input_blocked(is_speaking=False, now=10.1) is True

    gate.finish_output_turn(now=10.2)

    assert gate.mic_input_blocked(is_speaking=False, now=10.4) is True
    assert gate.mic_input_blocked(is_speaking=False, now=10.6) is False


def test_audio_gate_respects_current_speaking_flag():
    gate = AudioTurnGate()

    assert gate.mic_input_blocked(is_speaking=True, now=5.0) is True


def test_audio_gate_waits_for_drain_grace_before_releasing_turn():
    gate = AudioTurnGate(reopen_grace_seconds=0.35, drain_grace_seconds=0.45)
    gate.note_output_audio(now=20.0)

    assert gate.playback_drain_elapsed(now=20.2) is False
    assert gate.playback_drain_elapsed(now=20.5) is True


def test_audio_gate_reset_clears_blocking_state():
    gate = AudioTurnGate()
    gate.note_output_audio(now=30.0)
    gate.finish_output_turn(now=30.1)
    gate.reset()

    assert gate.mic_input_blocked(is_speaking=False, now=31.0) is False
    assert gate.playback_drain_elapsed(now=31.0) is True
