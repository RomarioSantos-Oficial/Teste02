from __future__ import annotations

import shutil
from pathlib import Path


PRIVATE_DATA_DIRECTORIES = (
    "online_debug",
    "online_profiles",
    "track_maps",
)


def ensure_private_data_directories(project_root: str | Path) -> tuple[Path, ...]:
    """Cria as pastas locais privadas sem alterar arquivos já existentes."""
    data_root = Path(project_root) / "data"
    directories: list[Path] = []
    for name in PRIVATE_DATA_DIRECTORIES:
        directory = data_root / name
        directory.mkdir(parents=True, exist_ok=True)
        directories.append(directory)
    return tuple(directories)


def clear_online_debug(project_root: str | Path) -> int:
    """Apaga somente o conteúdo temporário de ``data/online_debug``."""
    debug_directory = Path(project_root) / "data" / "online_debug"
    debug_directory.mkdir(parents=True, exist_ok=True)
    removed = 0
    for entry in tuple(debug_directory.iterdir()):
        if entry.is_symlink() or entry.is_file():
            entry.unlink()
        elif entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink(missing_ok=True)
        removed += 1
    return removed
