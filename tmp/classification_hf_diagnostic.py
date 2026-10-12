"""Inspect only the shape of a synthetic HF response; never print credentials."""
import json
from dataclasses import replace

from backend.ai.message_classification import MessageClassifier
from backend.config import Settings

config = replace(Settings.from_env(dotenv=True), message_classification_timeout_seconds=30)
classifier = MessageClassifier(config)
try:
    print("model=" + classifier.client.provider.model, flush=True)
    response = classifier.client._post(classifier.client._build_payload(
        classifier.prompt,
        json.dumps({"message": "Ce remedii naturiste există pentru gastrită?", "context": {"report_available": False}}),
        config.message_classification_max_output_tokens,
    ))
    payload = response.json()
    print(json.dumps({"status": payload.get("status"), "error": payload.get("error"), "incomplete_details": payload.get("incomplete_details"), "usage": payload.get("usage"), "output_types": [item.get("type") for item in payload.get("output", [])]}), flush=True)
    for item in payload.get("output", []):
        for block in item.get("content", []):
            print(json.dumps({"type": block.get("type"), "text": block.get("text", "")[:700]}), flush=True)
finally:
    classifier.close()
