from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .settings import CONFIG_FILE, ensure_dirs

def read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Warning: failed to read {path}: {exc}", file=sys.stderr)
    return default

def write_json(path: Path, data: Any) -> None:
    ensure_dirs()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)

def load_config() -> dict[str, Any]:
    config = read_json(CONFIG_FILE, {})
    return config if isinstance(config, dict) else {}
