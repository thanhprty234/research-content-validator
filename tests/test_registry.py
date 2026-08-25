"""Tests for agent registry (Phase 4.1)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agents.registry import load_registry


def test_load_registry_returns_four_agents():
    registry = load_registry()
    assert len(registry) == 4
    assert set(registry.keys()) == {"planner", "researcher", "writer", "critic"}


def test_agent_config_has_required_fields():
    registry = load_registry()
    for name, cfg in registry.items():
        assert hasattr(cfg, "module")
        assert hasattr(cfg, "class_name")
        assert cfg.module.startswith("agents.")


if __name__ == "__main__":
    test_load_registry_returns_four_agents()
    test_agent_config_has_required_fields()
    print("REGISTRY TEST OK")
