"""Workflow persistence for JARVIS.

Stores workflows and templates as JSON files on disk with
indexing support for search and listing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .models import Workflow, WorkflowStatus
from .templates import WorkflowTemplate

logger = logging.getLogger(__name__)


class WorkflowStore:
    """Persistent storage for workflows.

    Stores workflows as JSON files with indexing for search.
    Directory layout::

        <storage_path>/
            workflows/
                <workflow_id>.json
            templates/
                <template_name>.json
            index.json          # lightweight search index
    """

    def __init__(self, storage_path: str = "~/.jarvis/workflows") -> None:
        self._root = Path(storage_path).expanduser()
        self._workflows_dir = self._root / "workflows"
        self._templates_dir = self._root / "templates"
        self._index_path = self._root / "index.json"

        # Ensure directories exist
        self._workflows_dir.mkdir(parents=True, exist_ok=True)
        self._templates_dir.mkdir(parents=True, exist_ok=True)

        # Load or create index
        self._index: dict[str, dict[str, Any]] = self._load_index()

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def _load_index(self) -> dict[str, dict[str, Any]]:
        """Load the search index from disk."""
        if self._index_path.exists():
            try:
                return json.loads(self._index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load workflow index: %s", exc)
        return {}

    def _save_index(self) -> None:
        """Persist the search index to disk."""
        try:
            self._index_path.write_text(
                json.dumps(self._index, indent=2, default=str),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("Failed to save workflow index: %s", exc)

    def _index_workflow(self, workflow: Workflow) -> None:
        """Add or update a workflow entry in the index."""
        self._index[workflow.id] = {
            "id": workflow.id,
            "name": workflow.name,
            "status": workflow.status.value,
            "description": workflow.description,
            "tags": workflow.tags,
            "created_at": workflow.created_at.isoformat(),
            "updated_at": workflow.updated_at.isoformat(),
            "step_count": len(workflow.steps),
        }

    # ------------------------------------------------------------------
    # Workflow CRUD
    # ------------------------------------------------------------------

    def save(self, workflow: Workflow) -> Path:
        """Save a workflow to disk and update the index.

        Returns the path to the saved file.
        """
        path = self._workflows_dir / f"{workflow.id}.json"
        data = workflow.model_dump(mode="json")
        path.write_text(
            json.dumps(data, indent=2, default=str), encoding="utf-8"
        )
        self._index_workflow(workflow)
        self._save_index()
        logger.debug("Saved workflow %s to %s", workflow.id, path)
        return path

    def load(self, workflow_id: str) -> Workflow | None:
        """Load a workflow from disk by ID."""
        path = self._workflows_dir / f"{workflow_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Workflow.model_validate(data)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.error("Failed to load workflow %s: %s", workflow_id, exc)
            return None

    def delete(self, workflow_id: str) -> bool:
        """Delete a workflow from disk and the index. Returns True if found."""
        path = self._workflows_dir / f"{workflow_id}.json"
        if not path.exists():
            return False
        path.unlink()
        self._index.pop(workflow_id, None)
        self._save_index()
        logger.debug("Deleted workflow %s", workflow_id)
        return True

    def list_workflows(
        self, status: WorkflowStatus | None = None
    ) -> list[dict[str, Any]]:
        """List all workflows, optionally filtered by status.

        Returns lightweight index entries (not full workflow objects).
        """
        entries = list(self._index.values())
        if status is not None:
            entries = [e for e in entries if e.get("status") == status.value]
        # Sort by updated_at descending
        entries.sort(key=lambda e: e.get("updated_at", ""), reverse=True)
        return entries

    def search(self, query: str) -> list[dict[str, Any]]:
        """Search workflows by keyword (matches name, description, tags).

        Returns matching index entries.
        """
        q = query.lower()
        results: list[dict[str, Any]] = []
        for entry in self._index.values():
            name = entry.get("name", "").lower()
            desc = entry.get("description", "").lower()
            tags = [t.lower() for t in entry.get("tags", [])]
            if q in name or q in desc or any(q in t for t in tags):
                results.append(entry)
        return results

    # ------------------------------------------------------------------
    # Template CRUD
    # ------------------------------------------------------------------

    def save_template(self, template: WorkflowTemplate) -> Path:
        """Save a workflow template to disk.

        Returns the path to the saved file.
        """
        path = self._templates_dir / f"{template.name}.json"
        data = template.model_dump(mode="json")
        path.write_text(
            json.dumps(data, indent=2, default=str), encoding="utf-8"
        )
        logger.debug("Saved template %s to %s", template.name, path)
        return path

    def load_template(self, name: str) -> WorkflowTemplate | None:
        """Load a workflow template from disk by name."""
        path = self._templates_dir / f"{name}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return WorkflowTemplate.model_validate(data)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.error("Failed to load template %s: %s", name, exc)
            return None

    def list_templates(self) -> list[str]:
        """Return names of all saved templates."""
        return [
            p.stem
            for p in sorted(self._templates_dir.glob("*.json"))
        ]

    def delete_template(self, name: str) -> bool:
        """Delete a template by name. Returns True if found."""
        path = self._templates_dir / f"{name}.json"
        if not path.exists():
            return False
        path.unlink()
        logger.debug("Deleted template %s", name)
        return True
