"""Resolve catalog product images locally without exposing the source directory."""

from __future__ import annotations

import re
from pathlib import Path

import psycopg
from psycopg_pool import PoolTimeout

from backend.ai import db
from backend.ai.herb_repository import HerbCatalogUnavailable
from backend.config import Settings
from backend.core.operation_context import remaining_timeout


# Match the filenames produced by the local image-generation workflow on every OS.
def _filename(name: str) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name.strip()).rstrip(". ")
    return (stem + ".png").casefold() if stem and len(stem) <= 180 else ""


def resolve_herb_image(directory: Path, latin: str, romanian: str) -> Path | None:
    try:
        root = directory.resolve(strict=True)
        candidates: dict[str, list[Path]] = {}
        for entry in root.iterdir():
            if entry.suffix.casefold() == ".png":
                candidates.setdefault(entry.name.casefold(), []).append(entry)
        for name in (latin, romanian):
            matches = candidates.get(_filename(name), [])
            if len(matches) != 1:
                continue
            try:
                image = matches[0].resolve(strict=True)
                if (
                    image.is_relative_to(root)
                    and image.suffix.casefold() == ".png"
                    and image.is_file()
                ):
                    return image
            except (OSError, RuntimeError):
                continue
    except (OSError, RuntimeError):
        return None
    return None


def lookup_herb_image(herb_id: int, *, settings: Settings) -> Path | None:
    try:
        with (
            db.get_pool().connection(timeout=remaining_timeout(5.0)) as connection,
            connection.transaction(),
        ):
            connection.execute("SET TRANSACTION READ ONLY")
            connection.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (str(max(1, int(remaining_timeout(5.0) * 1000))),),
            )
            row = connection.execute(
                "SELECT latin, ro FROM herbs WHERE id = %s", (herb_id,)
            ).fetchone()
    except (psycopg.Error, PoolTimeout):
        raise HerbCatalogUnavailable() from None
    # Release the database connection before reading the optional image directory.
    return resolve_herb_image(settings.herb_images_dir, row[0] or "", row[1]) if row else None
