import base64
from pathlib import Path

source = base64.b64encode(Path("src/backend/ai/message_classification.py").read_bytes()).decode()
prompt = base64.b64encode(Path("src/backend/ai/prompts/message_classification_system.md").read_bytes()).decode()
providers = base64.b64encode(Path("src/backend/ai/providers.py").read_bytes()).decode()
client = base64.b64encode(Path("src/backend/ai/client.py").read_bytes()).decode()
checks = Path("tmp/ollama_classification_smoke/smoke.py").read_text(encoding="utf-8")
checks = checks[checks.index("classifier ="):].replace("module.MessageClassifier", "MessageClassifier")
script = f'''import base64, os
from types import SimpleNamespace
import backend.ai.providers as providers
exec(base64.b64decode('{providers}').decode(), providers.__dict__)
import backend.ai.client as client
exec(base64.b64decode('{client}').decode(), client.__dict__)
__file__ = '/app/backend/ai/message_classification.py'
exec(base64.b64decode('{source}').decode(), globals())
PROMPT = SimpleNamespace(read_text=lambda **kwargs: base64.b64decode('{prompt}').decode())
'''+checks
Path("tmp/ollama_stdin_smoke.py").write_text(script.encode("ascii", "backslashreplace").decode(), encoding="ascii")
