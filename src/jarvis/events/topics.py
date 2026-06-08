"""Standard event topics used across the JARVIS system.

Import ``Topics`` and reference constants like ``Topics.AGENT_COMPLETED``
when publishing or subscribing to events so that all modules share the
same canonical topic strings.
"""

from __future__ import annotations


class Topics:
    """Registry of well-known JARVIS event topics.

    Topics follow a hierarchical dot-separated naming scheme so that
    wildcard subscriptions (``agent.*``) are intuitive.
    """

    # -- Agent events ---------------------------------------------------------
    AGENT_REGISTERED = "agent.registered"
    AGENT_EXECUTING = "agent.executing"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    AGENT_DELEGATED = "agent.delegated"

    # -- Spec events ----------------------------------------------------------
    SPEC_CREATED = "spec.created"
    SPEC_EXECUTING = "spec.executing"
    SPEC_STEP_STARTED = "spec.step.started"
    SPEC_STEP_COMPLETED = "spec.step.completed"
    SPEC_STEP_FAILED = "spec.step.failed"
    SPEC_COMPLETED = "spec.completed"
    SPEC_FAILED = "spec.failed"
    SPEC_PAUSED = "spec.paused"
    SPEC_REDIRECTED = "spec.redirected"
    SPEC_CONSTRAINT_ADDED = "spec.constraint.added"
    SPEC_CONSTRAINT_REMOVED = "spec.constraint.removed"

    # -- Tool events ----------------------------------------------------------
    TOOL_CALLED = "tool.called"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"

    # -- LLM events -----------------------------------------------------------
    LLM_REQUEST = "llm.request"
    LLM_RESPONSE = "llm.response"
    LLM_ERROR = "llm.error"

    # -- Memory events --------------------------------------------------------
    MEMORY_ADDED = "memory.added"
    MEMORY_SEARCHED = "memory.searched"
    MEMORY_PRUNED = "memory.pruned"

    # -- Knowledge events -----------------------------------------------------
    KNOWLEDGE_EXTRACTED = "knowledge.extracted"
    KNOWLEDGE_QUERIED = "knowledge.queried"

    # -- Skill events ---------------------------------------------------------
    SKILL_DISTILLED = "skill.distilled"
    SKILL_EVOLVED = "skill.evolved"
    SKILL_EXECUTED = "skill.executed"

    # -- Curator events -------------------------------------------------------
    CURATOR_REVIEWED = "curator.reviewed"
    CURATOR_FLAGGED = "curator.flagged"

    # -- Session events -------------------------------------------------------
    SESSION_CREATED = "session.created"
    SESSION_COMPLETED = "session.completed"
    SESSION_EXPIRED = "session.expired"

    # -- Security events ------------------------------------------------------
    SECURITY_PERMISSION_DENIED = "security.permission_denied"
    SECURITY_SECRET_DETECTED = "security.secret_detected"
    SECURITY_COMMAND_BLOCKED = "security.command_blocked"

    # -- System events --------------------------------------------------------
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"
    SYSTEM_HEALTH_CHECK = "system.health_check"

    # -- Notification events --------------------------------------------------
    NOTIFICATION_SENT = "notification.sent"
    NOTIFICATION_FAILED = "notification.failed"

    # -- Workflow events ------------------------------------------------------
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_STEP_COMPLETED = "workflow.step.completed"
    WORKFLOW_APPROVAL_NEEDED = "workflow.approval.needed"
