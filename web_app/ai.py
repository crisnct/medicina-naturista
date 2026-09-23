"""Single-request report generation through the xAI Responses API."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx

from web_app.config import Settings

SECTIONS = ("uz_intern", "nutritie", "uz_extern", "alte_recomandari", "atentionari")
GENERATE_REPORT_SYSTEM_PROMPT_PATH = (
    Path(__file__).resolve().parent / "prompts" / "generate-raport-system-prompt.md"
)
UNSAFE = re.compile(
    r"\b(MMS|dioxid de clor|clorit de sodiu|argint coloidal|petrol|urinoterapie|"
    r"ulei(uri)? esen[țt]ial(e)? (ingerat|de b[ăa]ut)|opre[șs]te tratamentul)\b", re.I
)


class AIUnavailable(RuntimeError):
    pass


class XAIClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.http = httpx.Client(timeout=httpx.Timeout(75.0, connect=10.0))
        self.generate_system_prompt = GENERATE_REPORT_SYSTEM_PROMPT_PATH.read_text(
            encoding="utf-8"
        ).strip()

    def close(self) -> None:
        self.http.close()

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        key = self.settings.api_key()
        if not key:
            raise AIUnavailable("Lipsește GROK_API_KEY_MED. Configurați variabila în .env înainte de utilizare.")
        try:
            response = self.http.post(
                f"{self.settings.xai_api_base}/responses",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            return response
        except (httpx.HTTPError, ValueError) as exc:
            raise AIUnavailable("Serviciul AI nu este disponibil momentan. Încercați din nou.") from exc

    def complete_json(self, system: str, user: str, max_tokens: int) -> dict[str, Any]:
        response = self._post({
            "model": self.settings.xai_model,
            "reasoning": {"effort": self.settings.xai_reasoning_effort},
            "input": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "text": {"format": {"type": "json_object"}},
            "max_output_tokens": max_tokens,
            "store": False,
        })
        try:
            payload = response.json()
            if payload.get("status") != "completed":
                raise ValueError("response not completed")
            parts = [
                block["text"]
                for item in payload.get("output", [])
                if isinstance(item, dict) and item.get("type") == "message"
                for block in item.get("content", [])
                if isinstance(block, dict)
                and block.get("type") == "output_text"
                and isinstance(block.get("text"), str)
            ]
            content = "".join(parts)
            if not content:
                raise ValueError("empty content")
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ValueError("not an object")
            return result
        except (KeyError, ValueError, TypeError) as exc:
            raise AIUnavailable("Răspunsul AI nu a putut fi validat. Încercați din nou.") from exc

    def generate(
        self, profile: dict[str, Any], evidence: dict[str, dict[str, str]]
    ) -> dict[str, list[dict[str, Any]]]:
        if not evidence:
            return {name: [] for name in SECTIONS}
        entries = [
            {"id": token, "source": value["source"], "text": value["text"]}
            for token, value in evidence.items()
        ]
        user = f"""
            Contextul medical declarat de utilizator:
            {json.dumps(profile, ensure_ascii=False)}

            Toate fragmentele locale admise:
            {json.dumps(entries, ensure_ascii=False)}
        """.strip()
        result = self.complete_json(self.generate_system_prompt, user, 20000)
        sections: dict[str, list[dict[str, Any]]] = {name: [] for name in SECTIONS}
        for section in SECTIONS:
            items = result.get(section, [])
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                claim = item.get("text")
                ids = item.get("evidence_ids")
                if not isinstance(claim, str) or not isinstance(ids, list):
                    continue
                claim = " ".join(claim.split())[:650]
                valid_ids = [token for token in ids if isinstance(token, str) and token in evidence]
                if claim and valid_ids and not UNSAFE.search(claim):
                    sections[section].append({"text": claim, "evidence_ids": valid_ids[:5]})
        return sections
