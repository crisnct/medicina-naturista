import base64
from pathlib import Path

def encoded(path):
    return base64.b64encode(Path(path).read_bytes()).decode()

herbs = encoded("src/backend/ai/herbs.py")
repository = encoded("src/backend/ai/herb_repository.py")
classifier = encoded("src/backend/ai/message_classification.py")
prompt = encoded("src/backend/ai/prompts/message_classification_system.md")
script = f'''import os, base64
from types import SimpleNamespace
from backend.config import Settings, configure_settings
cfg=Settings.from_env(os.environ)
configure_settings(cfg)
import backend.ai.herbs as herbs
exec(base64.b64decode('{herbs}').decode(), herbs.__dict__)
import backend.ai.herb_repository as repository
exec(base64.b64decode('{repository}').decode(), repository.__dict__)
import backend.ai.message_classification as classifier
exec(base64.b64decode('{classifier}').decode(), classifier.__dict__)
classifier.PROMPT=SimpleNamespace(read_text=lambda **kwargs: base64.b64decode('{prompt}').decode())
c=classifier.MessageClassifier(cfg,herb_catalog=herbs.load_herbs)
try:
    for message,pending in [
        ('spune-mi tot ce stii despre coada-soricelului',None),
        ('coada-soricelului','planta'),
        ('musetel','planta'),
        ('papadie','planta'),
    ]:
        r=c(message,{{'pending_clarification':pending,'report_available':False,'herb_choices':[]}})
        print('message='+message+' intent='+r.intent+' plant='+str(r.herb_name)+' clarification='+str(r.needs_clarification),flush=True)
        assert r.intent=='planta' and r.herb_name and not r.needs_clarification
finally:
    c.close()
'''
Path("tmp/grounded_plant_stdin_smoke.py").write_text(script, encoding="ascii")
