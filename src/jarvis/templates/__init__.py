"""Template system for JARVIS.

Provides reusable templates for Streaming Specs, prompts, and other
structured content generation.
"""

from jarvis.templates.spec_templates import (
    SpecTemplate,
    StepTemplate,
    TemplateParameter,
)
from jarvis.templates.prompt_templates import PromptLibrary, PromptTemplate
from jarvis.templates.engine import TemplateEngine, TemplateRegistry

__all__ = [
    "PromptLibrary",
    "PromptTemplate",
    "SpecTemplate",
    "StepTemplate",
    "TemplateEngine",
    "TemplateParameter",
    "TemplateRegistry",
]
