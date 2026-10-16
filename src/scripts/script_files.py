"""Shared staging and publication of script outputs on their destination filesystem."""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

if __package__:
    from .script_logging import log_call
else:
    from script_logging import log_call

LOGGER = logging.getLogger(__name__)


@log_call
def _remove_temp(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        LOGGER.warning("Nu pot elimina fișierul temporar %s (%s).", path, type(exc).__name__)


@log_call
def _temporary_path(directory: Path, prefix: str = ".pdf-markdown-", suffix: str = "") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=prefix, suffix=suffix, dir=directory, delete=False
    ) as stream:
        return Path(stream.name)


@log_call
def _commit_outputs(outputs: dict[Path, Path]) -> None:
    """Publish prepared files, restoring previous files if any replacement fails."""
    if len(outputs) == 1:
        target, staged = next(iter(outputs.items()))
        staged.replace(target)
        return
    backups, committed, recovery = {}, [], set()
    try:
        for target in outputs:
            backups[target] = _temporary_path(target.parent) if target.exists() else None
            if backups[target] is not None:
                shutil.copyfile(target, backups[target])
        for target, staged in outputs.items():
            staged.replace(target)
            committed.append(target)
    except BaseException as exc:
        for target in reversed(committed):
            try:
                if backups[target] is None:
                    target.unlink()
                else:
                    backups[target].replace(target)
            except OSError:
                recovery.add(target)
        if recovery:
            raise RuntimeError(
                f"Restaurare incompletă; păstrați copiile de recuperare: "
                f"{[(str(target), str(backups[target])) for target in recovery]}"
            ) from exc
        raise
    finally:
        for target, backup in backups.items():
            if backup is not None and target not in recovery:
                _remove_temp(backup)
