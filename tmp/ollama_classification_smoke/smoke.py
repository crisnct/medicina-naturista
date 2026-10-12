import importlib.util
import os
from pathlib import Path

from backend.config import Settings

spec = importlib.util.spec_from_file_location("classification_smoke", Path(__file__).with_name("message_classification.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
classifier = module.MessageClassifier(Settings.from_env(os.environ))
try:
    for expected, message in [
        ("remedii", "Vreau remedii pentru gripă"),
        ("planta", "Ce afecțiuni sunt asociate cu mușețelul?"),
        ("diverse", "Cum funcționează căutarea semantică?"),
        ("email_raport", "Trimite raportul precedent la test@example.com"),
        ("diverse", "Nu trimite raportul la test@example.com"),
        ("remedii", "Ce plante ajută pentru gastrită?"),
    ]:
        try:
            result = classifier(message, {"report_available": True})
            print(f"expected={expected} actual={result.intent} clarification={result.needs_clarification}", flush=True)
            assert result.intent == expected, "Intent mismatch"
        except Exception as exc:
            print(f"failed={expected} type={type(exc).__name__}", flush=True)
            raise
finally:
    classifier.close()
