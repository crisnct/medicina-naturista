"""GBIF species-match lookups for the herbs_work scripts (stage E3/E4 of
architecture/plan-conditions-jsonl-si-herbs.md), cached in
tmp/herbs_work/gbif_cache.json so a rerun makes no new requests. Only plant,
fungus and alga names are sent."""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "tmp" / "herbs_work" / "gbif_cache.json"
API = "https://api.gbif.org/v1/species/match"
# Kingdoms of the catalogue: plants, fungi (lichens included), brown algae and
# other "algae" GBIF files under Chromista or Protozoa.
KINGDOMS = {"Plantae", "Fungi", "Chromista", "Protozoa"}

_lock = threading.Lock()


def _load() -> dict[str, dict]:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


_cache = _load()


def save() -> None:
    with _lock:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(_cache, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def match(name: str, rank: str | None = None, client: httpx.Client | None = None) -> dict:
    key = f"{rank or ''}|{name}"
    with _lock:
        if key in _cache:
            return _cache[key]
    params = {"name": name, "verbose": "false"}
    if rank:
        params["rank"] = rank
    owner = client or httpx.Client(timeout=30)
    try:
        for attempt in range(3):
            try:
                response = owner.get(API, params=params)
                response.raise_for_status()
                result = response.json()
                break
            except httpx.HTTPError:
                if attempt == 2:
                    raise
    finally:
        if client is None:
            owner.close()
    with _lock:
        _cache[key] = result
    return result


def match_many(names: list[str], rank: str | None = None, workers: int = 12) -> dict[str, dict]:
    with httpx.Client(timeout=30) as client, ThreadPoolExecutor(workers) as pool:
        results = dict(zip(names, pool.map(lambda name: match(name, rank, client), names)))
    save()
    return results


# Any other GBIF GET (distributions, vernacular names, occurrence counts), cached
# by URL and parameters.
def get(path: str, params: dict | None = None, client: httpx.Client | None = None) -> dict:
    key = f"GET|{path}|{json.dumps(params or {}, sort_keys=True)}"
    with _lock:
        if key in _cache:
            return _cache[key]
    owner = client or httpx.Client(timeout=30)
    try:
        for attempt in range(8):
            try:
                response = owner.get(f"https://api.gbif.org/v1/{path}", params=params)
                if response.status_code == 429:
                    # rate limited: wait as told, or back off exponentially
                    time.sleep(float(response.headers.get("Retry-After") or 2 ** attempt))
                    continue
                response.raise_for_status()
                result = response.json()
                break
            except httpx.HTTPError:
                if attempt == 7:
                    raise
                time.sleep(2 ** attempt)
        else:
            raise RuntimeError(f"GBIF kept rate-limiting {path}")
    finally:
        if client is None:
            owner.close()
    with _lock:
        _cache[key] = result
    return result


def get_many(requests: list[tuple[str, dict | None]], workers: int = 4) -> list[dict]:
    try:
        with httpx.Client(timeout=30) as client, ThreadPoolExecutor(workers) as pool:
            return list(pool.map(lambda item: get(item[0], item[1], client), requests))
    finally:
        save()


# The accepted species of a match, or None when GBIF does not know the name as a
# species (or lower) of one of KINGDOMS with enough confidence.
def accepted_species(result: dict, min_confidence: int = 90) -> str | None:
    if result.get("kingdom") not in KINGDOMS:
        return None
    if result.get("matchType") not in ("EXACT", "FUZZY") or result.get("confidence", 0) < min_confidence:
        return None
    if result.get("rank") not in ("SPECIES", "SUBSPECIES", "VARIETY", "FORM"):
        return None
    return result.get("species")
