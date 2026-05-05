from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
import pandas as pd

df = pd.read_csv("intents.csv")

X = df["text"]
y = df["intent"]

X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)

pipeline = Pipeline([
    ("tfdif", TfidfVectorizer()),
    ("clf", LogisticRegression(max_iter=1000))
])

pipeline.fit(X_train, y_train)
print(f"Accuracy: {pipeline.score(X_val, y_val) * 100:.2f}%")


test_phrases = [
    "можешь открыть телеграм",
    "вырубай звук",
    "спрячь окно",
    "запусти ютуб",
    "отключи микрофон пожалуйста",
]

for phrase in test_phrases:
    intent = pipeline.predict([phrase])[0]
    proba = pipeline.predict_proba([phrase]).max()
    print(f"{phrase:45} -> {intent:15} ({proba: .2f})")


import joblib
joblib.dump(pipeline, "intent_model.pkl")
print("Модель сохранена")