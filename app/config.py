"""Load project configuration and simple KEY=value environment overrides."""
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines() if (ROOT / ".env").exists() else []:
    if line.strip() and not line.lstrip().startswith("#") and "=" in line:
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
CONFIG = yaml.safe_load((ROOT / "configs/default.yaml").read_text(encoding="utf-8"))
