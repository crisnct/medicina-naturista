"""Single-request report generation through the xAI Responses API."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from web_app.config import Settings

logger = logging.getLogger("naturist.ai")
SECTIONS = ("uz_intern", "nutritie", "uz_extern", "alte_recomandari", "atentionari")
MAX_CONTEXT_CHARS = 2_400_000
GENERATE_REPORT_SYSTEM_PROMPT_PATH = (
    Path(__file__).resolve().parent / "prompts" / "generate-raport-system-prompt.md"
)
class AIUnavailable(RuntimeError):
    pass


class XAIClient:
    # Initialize the HTTP client and load the report-generation system prompt.
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.http = httpx.Client(timeout=httpx.Timeout(75.0, connect=10.0))
        self.generate_system_prompt = GENERATE_REPORT_SYSTEM_PROMPT_PATH.read_text(
            encoding="utf-8"
        ).strip()

    # Close the underlying HTTP connection pool.
    def close(self) -> None:
        self.http.close()

    # Send one authenticated request to the xAI Responses API with diagnostic logging.
    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        key = self.settings.api_key()
        if not key:
            logger.error("ai_request_skipped reason=missing_api_key")
            raise AIUnavailable("Lipsește GROK_API_KEY_MED. Configurați variabila în .env înainte de utilizare.")
        started = time.perf_counter()
        logger.info(
            "ai_request_started model=%s reasoning_effort=%s max_output_tokens=%s",
            payload.get("model"),
            payload.get("reasoning", {}).get("effort"),
            payload.get("max_output_tokens"),
        )
        try:
            response = self.http.post(
                f"{self.settings.xai_api_base}/responses",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            logger.info(
                "ai_request_completed status=%s duration_ms=%s response_bytes=%s request_id=%s",
                getattr(response, "status_code", "-"),
                round((time.perf_counter() - started) * 1000),
                len(getattr(response, "content", b"")),
                getattr(response, "headers", {}).get("x-request-id")
                or getattr(response, "headers", {}).get("request-id")
                or "-",
            )
            return response
        except httpx.HTTPStatusError as exc:
            response = exc.response
            request_id = response.headers.get("x-request-id") or response.headers.get("request-id") or "-"
            body = response.text.strip() or "<empty response body>"
            logger.error(
                "ai_request_failed status=%s duration_ms=%s request_id=%s body=%s",
                response.status_code,
                round((time.perf_counter() - started) * 1000),
                request_id,
                body[:12000],
            )
            raise AIUnavailable(
                f"Serviciul AI a respins cererea (HTTP {response.status_code}, request_id={request_id})."
            ) from exc
        except httpx.RequestError as exc:
            logger.error(
                "ai_request_failed error=request duration_ms=%s message=%s",
                round((time.perf_counter() - started) * 1000),
                str(exc),
            )
            raise AIUnavailable("Serviciul AI nu este disponibil momentan. Încercați din nou.") from exc
        except ValueError as exc:
            logger.error(
                "ai_request_failed error=invalid_response duration_ms=%s message=%s",
                round((time.perf_counter() - started) * 1000),
                str(exc),
            )
            raise AIUnavailable("Serviciul AI nu este disponibil momentan. Încercați din nou.") from exc

    # Request a JSON response from xAI and validate its top-level structure.
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
            logger.info(
                "ai_response_parsed content_chars=%s top_level_keys=%s",
                len(content),
                len(result),
            )
            return result
        except (KeyError, ValueError, TypeError) as exc:
            logger.error("ai_response_invalid message=%s", str(exc))
            raise AIUnavailable("Răspunsul AI nu a putut fi validat. Încercați din nou.") from exc

    # Log fragment counts, documents, metadata, and optionally fragment text at a pipeline stage.
    def _log_fragment_inventory(
        self,
        entries: list[dict[str, str]],
        event: str,
        original_lengths: dict[str, int] | None = None,
    ) -> None:
        """Log the exact evidence inventory at one context-building stage.

        Fragment text logging is intentionally configurable because the evidence
        can contain sensitive medical details. Source and line metadata remain
        available even when text logging is disabled.
        """
        lengths = [len(entry["text"]) for entry in entries]
        total_chars = sum(lengths)
        unique_source_files = {entry["source"].split(":", 1)[0] for entry in entries}
        logger.info(
            "%s count=%s total_chars=%s approx_tokens=%s "
            "documents_count=%s min_chars=%s max_chars=%s text_logging=%s",
            event,
            len(entries),
            total_chars,
            total_chars // 4,
            len(unique_source_files),
            min(lengths, default=0),
            max(lengths, default=0),
            self.settings.log_fragment_text,
        )
        for document in sorted(unique_source_files):
            logger.info("%s_document source=%s", event, document)
        for position, entry in enumerate(entries, start=1):
            text = entry["text"]
            logged_text = (
                text[: self.settings.log_fragment_text_max_chars]
                if self.settings.log_fragment_text
                else "<disabled>"
            )
            logger.info(
                "%s_fragment %s",
                event,
                json.dumps(
                    {
                        "position": position,
                        "id": entry["id"],
                        "source": entry["source"],
                        "text_chars": len(text),
                        "text_logged_chars": len(logged_text) if self.settings.log_fragment_text else 0,
                        "text_truncated_in_log": bool(
                            self.settings.log_fragment_text and len(logged_text) < len(text)
                        ),
                        "original_text_chars": (
                            original_lengths.get(entry["id"], len(text))
                            if original_lengths is not None
                            else len(text)
                        ),
                        "compaction_removed_chars": (
                            max(0, original_lengths.get(entry["id"], len(text)) - len(text))
                            if original_lengths is not None
                            else 0
                        ),
                        "text": logged_text,
                    },
                    ensure_ascii=False,
                ),
            )

    # Convert evidence to AI input entries and compact text only when the context limit is exceeded.
    def _evidence_entries(self, evidence: dict[str, dict[str, str]]) -> list[dict[str, str]]:
        entries = [
            {"id": token, "source": value["source"], "text": value["text"]}
            for token, value in evidence.items()
        ]
        serialized_length = len(json.dumps(entries, ensure_ascii=False))
        if serialized_length <= MAX_CONTEXT_CHARS:
            return entries

        original_length = serialized_length
        original_lengths = {entry["id"]: len(entry["text"]) for entry in entries}
        self._log_fragment_inventory(entries, "fragments_before_compaction")
        text_length = sum(len(entry["text"]) for entry in entries)
        fixed_length = serialized_length - text_length
        available_text = max(0, MAX_CONTEXT_CHARS - fixed_length)
        scale = available_text / text_length if text_length else 0
        for entry in entries:
            original_text = entry["text"]
            keep = min(len(original_text), max(256, int(len(original_text) * scale)))
            entry["text"] = original_text[:keep]

        # JSON punctuation and source strings can push the first estimate over
        # the budget. Trim evenly while retaining every evidence entry and ID.
        while len(json.dumps(entries, ensure_ascii=False)) > MAX_CONTEXT_CHARS:
            candidates = [entry for entry in entries if len(entry["text"]) > 256]
            if not candidates:
                break
            trim = max(1, (len(json.dumps(entries, ensure_ascii=False)) - MAX_CONTEXT_CHARS) // len(candidates))
            for entry in candidates:
                entry["text"] = entry["text"][:-trim]

        compacted_length = len(json.dumps(entries, ensure_ascii=False))
        logger.warning(
            "fragment_compaction_completed entries=%s serialized_chars=%s->%s limit=%s "
            "text_chars_removed=%s",
            len(entries),
            original_length,
            compacted_length,
            MAX_CONTEXT_CHARS,
            sum(original_lengths.values()) - sum(len(entry["text"]) for entry in entries),
        )
        self._log_fragment_inventory(entries, "fragments_sent_to_ai", original_lengths)
        return entries

    # Send the full evidence context to xAI and normalize all returned report sections.
    # Normalize the structured nutrition object into the internal recommendation-item format.
    def _normalize_nutrition_section(self, value: Any) -> list[dict[str, Any]]:
        fields = (
            ("retete", "[RETETA]"),
            ("recomandate", "[RECOMANDAT]"),
            ("nerecomandate", "[NERECOMANDAT]"),
            ("interzise", "[INTERZIS]"),
            ("alte", "[ALTE]"),
        )
        normalized: list[dict[str, Any]] = []
        if not isinstance(value, dict):
            return normalized
        for field, prefix in fields:
            raw_values = value.get(field)
            if isinstance(raw_values, list):
                values = raw_values
            elif raw_values is None:
                values = []
            else:
                values = [raw_values]
            for raw_value in values:
                evidence_ids: list[str] = []
                if isinstance(raw_value, dict):
                    claim = raw_value.get("text")
                    raw_ids = raw_value.get("evidence_ids", [])
                    if isinstance(raw_ids, list):
                        evidence_ids = [token for token in raw_ids if isinstance(token, str)]
                elif isinstance(raw_value, str):
                    claim = raw_value
                else:
                    continue
                if not isinstance(claim, str):
                    continue
                claim = self._normalize_claim(claim)
                if not claim or claim.strip(" -•\n\t") == "":
                    continue
                normalized.append({
                    "text": f"{prefix}: {claim}",
                    "evidence_ids": evidence_ids,
                })
        return normalized

    # Preserve meaningful line breaks while normalizing text returned by the AI.
    @staticmethod
    def _normalize_claim(claim: str) -> str:
        return "\n".join(
            line.strip()
            for line in claim.replace("\r\n", "\n").split("\n")
            if line.strip()
        )

    # Send the full evidence context to xAI and normalize all returned report sections.
    def generate(
        self, profile: dict[str, Any], evidence: dict[str, dict[str, str]]
    ) -> dict[str, list[dict[str, Any]]]:
        if not evidence:
            logger.info("fragments_sent_to_ai count=0 reason=no_evidence")
            return {name: [] for name in SECTIONS}
        logger.info(
            "fragments_collected_for_ai count=%s total_chars=%s",
            len(evidence),
            sum(len(value.get("text", "")) for value in evidence.values()),
        )
        entries = self._evidence_entries(evidence)
        if len(json.dumps(entries, ensure_ascii=False)) <= MAX_CONTEXT_CHARS:
            self._log_fragment_inventory(entries, "fragments_sent_to_ai")
        user = f"""
            Problema pentru care se solicită recomandări naturiste:
            {json.dumps(profile, ensure_ascii=False)}

            Toate fragmentele locale admise:
            {json.dumps(entries, ensure_ascii=False)}
        """.strip()
        logger.info(
            "xAI request user payload prepared: chars=%s approx_tokens=%s evidence_entries=%s",
            len(user),
            len(user) // 4,
            len(entries),
        )
        result = self.complete_json(self.generate_system_prompt, user, 20000)
        sections: dict[str, list[dict[str, Any]]] = {name: [] for name in SECTIONS}
        for section in SECTIONS:
            items = result.get(section, [])
            if section == "nutritie" and isinstance(items, dict):
                sections[section] = self._normalize_nutrition_section(items)
                continue
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                claim = item.get("text")
                if not isinstance(claim, str):
                    continue
                ids = item.get("evidence_ids", [])
                if not isinstance(ids, list):
                    ids = []
                claim = self._normalize_claim(claim)
                evidence_ids = [token for token in ids if isinstance(token, str)]
                if claim:
                    sections[section].append({"text": claim, "evidence_ids": evidence_ids})
        logger.info(
            "ai_report_sections_completed total_items=%s %s",
            sum(len(items) for items in sections.values()),
            " ".join(f"{name}={len(sections[name])}" for name in SECTIONS),
        )
        return sections
