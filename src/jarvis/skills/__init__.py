"""JARVIS Skills — reusable, self-improving procedural memory.

Skills are the bridge between Streaming Specs and persistent knowledge.
When an Agent completes a Spec successfully, the procedure can be distilled
into a Skill for future reuse.  Skills improve over time through the
evolution loop driven by :class:`SkillEvolver`.
"""

from jarvis.skills.base import Skill, SkillMetadata, SkillStatus
from jarvis.skills.registry import SkillRegistry
from jarvis.skills.evolve import SkillEvolver
from jarvis.skills.eval import SkillEvaluator, EvalCase, EvalSuite, EvalType
from jarvis.skills.failure_analyzer import FailureAnalyzer, FailureType

__all__ = [
    "Skill", "SkillMetadata", "SkillStatus", "SkillRegistry", "SkillEvolver",
    "SkillEvaluator", "EvalCase", "EvalSuite", "EvalType",
    "FailureAnalyzer", "FailureType",
]
