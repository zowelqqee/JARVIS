from fastapi import FastAPI
import joblib
from pydantic import BaseModel

app = FastAPI()
pipeline = joblib.load("intent_model.pkl")

class Query(BaseModel):
    text: str

@app.post("/predict")
def predict_intent(query: Query):
    intent = pipeline.predict([query.text])[0]
    proba = pipeline.predict_proba([query.text]).max()
    return {
        "intent": intent,
        "confidence": float(f"{proba:.2f}")
    }