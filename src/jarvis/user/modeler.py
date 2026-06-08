from __future__ import annotations

import logging
from pathlib import Path

from jarvis.user.profile import UserProfile

logger = logging.getLogger(__name__)


class UserModeler:
    """Learns and updates user profile over time.

    Analyzes interactions to build a richer understanding of the user:
    - Infer expertise from questions asked and tasks completed
    - Track preference patterns (time of day, tools used)
    - Update communication style based on feedback
    - Generate personalized context for agents
    """

    def __init__(
        self,
        profile: UserProfile | None = None,
        storage_path: str = "~/.jarvis/user",
    ):
        self._profile = profile or UserProfile()
        self._storage_path = Path(storage_path).expanduser()

    @property
    def profile(self) -> UserProfile:
        return self._profile

    async def on_interaction(
        self, agent_name: str, message: str, tool_name: str = ""
    ) -> None:
        """Called after each user interaction to update the model."""
        self._profile.record_interaction(
            agent_name=agent_name, tool_name=tool_name
        )
        self._infer_from_message(message)
        self.save()

    def _infer_from_message(self, message: str) -> None:
        """Infer user characteristics from message content."""
        msg_lower = message.lower()

        # Infer code language preference
        lang_hints: dict[str, list[str]] = {
            "python": ["python", "pip", "django", "flask", "fastapi", "pandas"],
            "javascript": [
                "javascript",
                "js",
                "node",
                "react",
                "vue",
                "npm",
            ],
            "go": ["golang", "go ", "gin ", "goroutine"],
            "rust": ["rust", "cargo", "tokio"],
            "java": ["java ", "spring", "maven", "gradle"],
        }
        for lang, hints in lang_hints.items():
            if any(h in msg_lower for h in hints):
                if not self._profile.preferences.code_language:
                    self._profile.preferences.code_language = lang

        # Infer expertise domains
        domain_hints: dict[str, list[str]] = {
            "backend": ["api", "server", "database", "endpoint", "backend"],
            "frontend": [
                "react",
                "css",
                "html",
                "ui",
                "frontend",
                "component",
            ],
            "devops": ["docker", "k8s", "kubernetes", "ci/cd", "deploy"],
            "data": ["data", "analytics", "machine learning", "ml", "pandas"],
            "security": ["security", "vulnerability", "owasp", "auth"],
        }
        for domain, hints in domain_hints.items():
            if any(h in msg_lower for h in hints):
                if self._profile.get_expertise_level(domain) == "unknown":
                    self._profile.add_expertise(domain, "intermediate")

    def get_context_for_agent(self, agent_name: str) -> str:
        """Generate personalized context for a specific agent."""
        return self._profile.to_context_string()

    def save(self) -> None:
        self._profile.save(self._storage_path / "profile.json")

    def load(self) -> None:
        path = self._storage_path / "profile.json"
        if path.exists():
            self._profile = UserProfile.load(path)
