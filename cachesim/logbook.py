"""Automatic logging — appends to logs/experiment_log.md on every action."""
from __future__ import annotations

import datetime
import platform
import sys
from pathlib import Path

import config as cfg


def _versions() -> dict:
    versions = {"python": sys.version.split()[0], "platform": platform.platform()}
    try:
        import numpy; versions["numpy"] = numpy.__version__
    except Exception:
        pass
    try:
        import pandas; versions["pandas"] = pandas.__version__
    except Exception:
        pass
    try:
        import streamlit; versions["streamlit"] = streamlit.__version__
    except Exception:
        pass
    return versions


def log_event(action: str, details: dict | None = None) -> None:
    cfg.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = cfg.LOGS_DIR / "experiment_log.md"
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    versions = _versions()

    lines = [
        f"\n## {action} — {ts}\n",
        f"- **Python**: {versions.get('python', '?')}",
        f"- **Platform**: {versions.get('platform', '?')}",
        f"- **numpy**: {versions.get('numpy', '?')}",
        f"- **pandas**: {versions.get('pandas', '?')}",
    ]
    if details:
        for k, v in details.items():
            lines.append(f"- **{k}**: {v}")
    lines.append("")

    with open(log_path, "a") as f:
        f.write("\n".join(lines) + "\n")
