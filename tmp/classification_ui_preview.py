"""Preview the real built UI against synthetic infrastructure on a separate port."""
import time
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.ai.message_classification import MessageClassification
from backend.core.models import CommitChange, StoredReport
from tests.unit.web import test_web as support

fixture = support.WebTests()
fixture.setUp()
fixture.deps.retriever.category_tree = None
fixture.deps.retriever.document_count = 1
fixture.deps.settings = fixture.deps.store.limits = __import__("dataclasses").replace(
    fixture.deps.settings, max_requests_per_minute=300,
)


def classify(message, context):
    time.sleep(0.6)
    if "@" in message or "trimite" in message.casefold():
        return MessageClassification(intent="email_raport")
    if "musetel" in message.casefold() or "mușețel" in message.casefold():
        return MessageClassification(intent="planta", herb_name="musetel")
    return MessageClassification(intent="diverse")


fixture.deps.classify = classify
fixture.deps.email = lambda *args: "sent"
fixture.deps.herb_lookup = lambda name: {
    "status": "found", "herbName": "mușețel", "species": ["matricaria chamomilla", "chamaemelum nobile"],
    "entriesCount": 3,
    "conditions": [{"id": 11, "name": "Gastrită"}, {"id": 25, "name": "Insomnie"}, {"id": 42, "name": "Stomatită"}],
}
app = fixture.client.app
app.get("/preview-diagram.svg")(lambda: FileResponse(Path("architecture/chatbot-external-connections.svg")))
app.mount("/", StaticFiles(directory="src/frontend/dist", html=True))
