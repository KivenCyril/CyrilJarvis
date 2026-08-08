from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class TriggerDef(BaseModel):
    event: str
    filter: str = ""


class CapabilitiesDef(BaseModel):
    skills: list[str] = Field(default_factory=list)
    input_modes: list[str] = Field(default_factory=list)
    output_modes: list[str] = Field(default_factory=list)


class RuleDef(BaseModel):
    name: str
    severity: str = "P2"
    description: str = ""


class ContextDef(BaseModel):
    knowledge_base: str = ""
    memory_scope: str = "per-user"


class CollaborationDef(BaseModel):
    can_delegate_to: list[str] = Field(default_factory=list)
    escalate_to: list[str] = Field(default_factory=list)
    escalate_condition: str = ""


class AgentSpecMetadata(BaseModel):
    name: str
    version: str = "v1.0"
    domain: str = ""


class AgentSpec(BaseModel):
    kind: str = "AgentSpec"
    metadata: AgentSpecMetadata
    triggers: list[TriggerDef] = Field(default_factory=list)
    capabilities: CapabilitiesDef = Field(default_factory=CapabilitiesDef)
    rules: list[RuleDef] = Field(default_factory=list)
    context: ContextDef = Field(default_factory=ContextDef)
    collaboration: CollaborationDef = Field(default_factory=CollaborationDef)

    @classmethod
    def from_yaml(cls, path: str | Path) -> AgentSpec:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, list):
            data = data[0]
        collab = data.get("collaboration", {})
        if "escalate_to" in collab and isinstance(collab["escalate_to"], list):
            items = collab["escalate_to"]
            cleaned = []
            for item in items:
                if isinstance(item, dict) and "condition" in item:
                    collab["escalate_condition"] = item["condition"]
                else:
                    cleaned.append(item)
            collab["escalate_to"] = cleaned
        return cls.model_validate(data)
