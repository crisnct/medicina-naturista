"""Live classification only, with synthetic questions and no email delivery."""
import json
import time

from backend.ai.message_classification import MessageClassifier
from backend.config import Settings

config = Settings.from_env(dotenv=True)
classifier = MessageClassifier(config)
try:
    for message, expected in [
        ("Ce remedii naturiste există pentru gastrită?", "remedii"),
        ("Pentru ce afecțiuni este folosit mușețelul?", "planta"),
        ("Cum se prepară o infuzie?", "diverse"),
        ("Trimite raportul precedent la synthetic@example.com", "email_raport"),
    ]:
        started = time.monotonic()
        try:
            result = classifier(message, {"report_available": True, "pending_clarification": None, "herb_choices": []})
            print(json.dumps({"expected": expected, "actual": result.intent, "correct": result.intent == expected, "seconds": round(time.monotonic()-started, 2)}, ensure_ascii=True), flush=True)
        except Exception as exc:
            print(json.dumps({"expected": expected, "error_type": type(exc).__name__, "message": str(exc), "seconds": round(time.monotonic()-started, 2)}), flush=True)
            break
finally:
    classifier.close()
