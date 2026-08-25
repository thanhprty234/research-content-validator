"""Agent registry — load agents from config YAML."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "agents.yaml"


@dataclass
class AgentConfig:
    module: str
    class_name: str
    model: Optional[str] = None


def load_registry(path: Optional[Path] = None) -> dict[str, AgentConfig]:
    """Load agent registry from YAML. Returns dict of name -> AgentConfig."""
    config_path = path or _CONFIG_PATH
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        data = yaml.safe_load(f) or {}
    agents = {}
    for name, cfg in data.get("agents", {}).items():
        agents[name] = AgentConfig(
            module=cfg["module"],
            class_name=cfg["class"],
            model=cfg.get("model"),
        )
    return agents
