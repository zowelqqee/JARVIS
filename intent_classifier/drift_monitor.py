import pandas as pd
import numpy as np
from scipy import stats
import joblib

pipeline = joblib.load("intent_classifier/intent_model.pkl")

# Референс — уверенность модели на обучающих данных
reference = pd.read_csv("intent_classifier/intents.csv")
ref_proba = pipeline.predict_proba(reference["text"]).max(axis=1)

# Текущие данные — другой домен
current_data = [
    "какая погода завтра",
    "переведи текст на английский",
    "сколько стоит биткоин",
    "напиши письмо другу",
    "найди рецепт борща",
    "расскажи анекдот",
    "включи таймер на 10 минут",
    "позвони маме",
]
cur_proba = pipeline.predict_proba(current_data).max(axis=1)

print(f"Средняя уверенность на обучающих данных: {ref_proba.mean():.3f}")
print(f"Средняя уверенность на текущих данных:   {cur_proba.mean():.3f}")

stat, p_value = stats.ks_2samp(ref_proba, cur_proba)
print(f"\nKS тест p-value: {p_value:.4f}")

if p_value < 0.05:
    print("⚠️ ALERT: drift обнаружен — модель неуверена в новых данных")
else:
    print("✅ Drift в норме")