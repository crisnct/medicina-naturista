"""Exercise real plant routes in a new, synthetic session without generating reports."""
import os
import time
import httpx
from backend.config import Settings

cfg = Settings.from_env(os.environ)
base = "http://medicina:7860" + cfg.public_root_path + "/"
with httpx.Client(base_url=base, headers={"X-Tab-Id":"codex-plant-regression01", "Origin":cfg.public_origin or "http://127.0.0.1:7860"}, timeout=30) as client:
    for attempt in range(35):
        try:
            health = client.get("healthz")
            health.raise_for_status()
            break
        except httpx.HTTPError:
            time.sleep(1)
    else:
        raise RuntimeError("App health unavailable")
    client.get("api/session").raise_for_status()
    client.headers["Cookie"]="naturist_sid="+client.cookies.get("naturist_sid")
    try:
        def send(message):
            accepted=client.post("api/messages",json={"message":message,"categories":[]})
            accepted.raise_for_status()
            result=client.post("api/classify",headers={"X-Context-Revision":str(accepted.json()["contextRevision"])})
            result.raise_for_status()
            payload=result.json()
            print("message="+message+" intent="+str(payload.get("intent"))+" kinds="+str([item["kind"] for item in payload["messages"]]),flush=True)
            return payload
        result=send("spune-mi tot ce stii despre coada-soricelului")
        assert any(item["kind"]=="herb_conditions" for item in result["messages"]), result
        result=send("musetel")
        assert any("Alegeți una" in item.get("content", "") for item in result["messages"]), result
        print("Choices offered for musetel",flush=True)
        result=send("musetel roman")
        panel=next(item for item in result["messages"] if item["kind"]=="herb_conditions")
        assert panel["species"]==["chamaemelum nobile"], panel
        print("selected species="+str(panel["species"])+" entries="+str(panel["entriesCount"]),flush=True)
    finally:
        client.post("api/session/unload").raise_for_status()
