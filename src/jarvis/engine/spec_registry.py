from __future__ import annotations

import logging
from pathlib import Path

from jarvis.models.agent_spec import AgentSpec

logger = logging.getLogger(__name__)


class SpecRegistry:
    """Registry for static AgentSpec definitions loaded from YAML files."""

    def __init__(self, specs_dir: str | Path | None = None) -> None:
        self._specs: dict[str, AgentSpec] = {}
        if specs_dir:
            self.load_dir(specs_dir)

    def load_dir(self, specs_dir: str | Path) -> int:
        specs_dir = Path(specs_dir)
        count = 0
        for yaml_file in specs_dir.rglob("*.yaml"):
            try:
                spec = AgentSpec.from_yaml(yaml_file)
                self._specs[spec.metadata.name] = spec
                count += 1
                logger.info("Loaded AgentSpec: %s (v%s)", spec.metadata.name, spec.metadata.version)
            except Exception as e:
                logger.warning("Failed to load %s: %s", yaml_file, e)
        return count

    def get(self, name: str) -> AgentSpec | None:
        return self._specs.get(name)

    def list_specs(self) -> list[AgentSpec]:
        return list(self._specs.values())

    def register(self, spec: AgentSpec) -> None:
        self._specs[spec.metadata.name] = spec
