import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import joblib

MODEL_PATH = os.path.join(os.path.dirname(__file__), "intent_model.pkl")
pipeline = joblib.load(MODEL_PATH)

KNOWN_INTENTS = {"open_app", "close_app", "minimize_app", "maximize_app", "turn_on", "turn_off"}

def test_model_loads():
    assert pipeline is not None 

def test_predict_returns_known_intent():
    result = pipeline.predict(["открой браузер"])[0]
    assert result in KNOWN_INTENTS

def test_confidence_range():
    proba = pipeline.predict_proba(["открой браузер"])[0].max()
    assert 0.0 <= proba <= 1.0

def test_multiple_phrases():
    phrases = ["открой браузер", "закрой браузер", "сверни окно", "разверни окно", "включи свет", "выключи свет"]
    results = pipeline.predict(phrases)
    for r in results:
        assert r in KNOWN_INTENTS
        