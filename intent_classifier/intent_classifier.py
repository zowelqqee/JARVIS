import joblib
import numpy as np

class IntentClassifier:
    def __init__ (self, model_path="intent_model.pkl", threshold=0.6):
        self.model = joblib.load(model_path)
        self.threshold = threshold
    
    def classify(self, text: str) -> dict:
        proba = self.model.predict_proba([text])[0]
        max_idx = np.argmax(proba)
        confidence = float(proba[max_idx])
        intent = self.model.classes_[max_idx]
        return {
            "intent": intent if confidence >= self.threshold else "unknown",
            "confidence": confidence,
            "raw_text": text
        }
