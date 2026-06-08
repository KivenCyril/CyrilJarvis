"""English (en) string table for JARVIS."""

STRINGS: dict[str, str] = {
    # ── System ──────────────────────────────────────────────────────────
    "system.name": "JARVIS",
    "system.version": "v0.2.0",
    "system.welcome": "Welcome to JARVIS -- your personal AI assistant",
    "system.goodbye": "Goodbye!",
    "system.initializing": "Initializing JARVIS...",
    "system.ready": "System ready: {agent_count} agents, {tool_count} tools",
    "system.shutting_down": "Shutting down...",
    "system.uptime": "Uptime: {hours}h {minutes}m",
    "system.version_info": "JARVIS {version} (Python {python_version})",
    "system.update_available": "Update available: {new_version}",

    # ── Agents ──────────────────────────────────────────────────────────
    "agent.registered": "Agent '{name}' registered",
    "agent.not_found": "Agent '{name}' not found",
    "agent.routing_to": "Routing to '{name}' (score={score})",
    "agent.no_handler": "No agent can handle this request",
    "agent.execution_failed": "Agent '{name}' failed: {error}",
    "agent.execution_started": "Agent '{name}' started processing",
    "agent.execution_completed": "Agent '{name}' completed in {duration}ms",
    "agent.idle": "Agent '{name}' is idle",
    "agent.busy": "Agent '{name}' is busy",
    "agent.shutdown": "Agent '{name}' shut down",
    "agent.code.description": "Code review, generation, git operations, and build management",
    "agent.knowledge.description": "Information retrieval, document Q&A, and knowledge graph queries",
    "agent.calendar.description": "Schedule management, conflict detection, and meeting preparation",
    "agent.comms.description": "Email triage, message summarization, draft replies, and notifications",
    "agent.ops.description": "Monitoring, alert diagnosis, deployment, and incident response",
    "agent.data.description": "Data analysis, statistics, visualization, and transformation",
    "agent.security.description": "Security auditing, vulnerability scanning, and compliance",
    "agent.devops.description": "Docker, Kubernetes, CI/CD, and infrastructure management",
    "agent.writing.description": "Technical writing, documentation, and content creation",
    "agent.research.description": "Deep research, analysis, and report generation",

    # ── Specs ───────────────────────────────────────────────────────────
    "spec.created": "Created Streaming Spec: {id}",
    "spec.executing": "Executing spec '{name}'...",
    "spec.completed": "Spec completed: {progress}",
    "spec.failed": "Spec failed: {error}",
    "spec.paused": "Spec paused",
    "spec.resumed": "Spec resumed",
    "spec.cancelled": "Spec cancelled",
    "spec.redirected": "Spec redirected to: {intent}",
    "spec.step.pending": "Pending",
    "spec.step.ready": "Ready",
    "spec.step.blocked": "Blocked (waiting for dependencies)",
    "spec.step.executing": "Executing...",
    "spec.step.completed": "Completed",
    "spec.step.failed": "Failed",
    "spec.step.skipped": "Skipped",
    "spec.step.cancelled": "Cancelled",
    "spec.constraint.added": "Constraint added: {content}",
    "spec.constraint.removed": "Constraint removed",
    "spec.constraint.modified": "Constraint modified",
    "spec.dag.valid": "DAG validation passed",
    "spec.dag.cycle_detected": "Cycle detected in dependency graph",
    "spec.progress": "Progress: {done}/{total} ({pct}%)",

    # ── Tools ───────────────────────────────────────────────────────────
    "tool.registered": "Tool '{name}' registered",
    "tool.not_found": "Tool '{name}' not found",
    "tool.execution.success": "Tool '{name}' executed successfully",
    "tool.execution.failed": "Tool '{name}' failed: {error}",
    "tool.execution.timeout": "Tool '{name}' timed out after {seconds}s",
    "tool.blocked": "Command blocked for safety: {reason}",
    "tool.approval_required": "Tool '{name}' requires human approval",
    "tool.approved": "Tool '{name}' approved",
    "tool.denied": "Tool '{name}' denied",

    # ── Memory ──────────────────────────────────────────────────────────
    "memory.added": "Memory added (importance={importance})",
    "memory.updated": "Memory updated: {id}",
    "memory.deleted": "Memory deleted: {id}",
    "memory.search.results": "Found {count} relevant memories",
    "memory.search.empty": "No matching memories found",
    "memory.pruned": "Pruned {count} old memories",
    "memory.capacity": "Memory usage: {used}/{total}",

    # ── Knowledge ───────────────────────────────────────────────────────
    "knowledge.extracted": "Extracted {count} entities",
    "knowledge.query.results": "Found {count} relevant nodes",
    "knowledge.saved": "Knowledge graph saved ({nodes} nodes, {edges} edges)",
    "knowledge.loaded": "Knowledge graph loaded ({nodes} nodes, {edges} edges)",
    "knowledge.node.added": "Node added: {label}",
    "knowledge.edge.added": "Edge added: {source} -> {target}",

    # ── Skills ──────────────────────────────────────────────────────────
    "skill.distilled": "Skill distilled from spec: {name}",
    "skill.evolved": "Skill evolved: {name} v{version}",
    "skill.loaded": "Loaded {count} skills",
    "skill.applied": "Skill applied: {name}",
    "skill.not_found": "Skill '{name}' not found",

    # ── Curator ─────────────────────────────────────────────────────────
    "curator.approved": "Review: APPROVED (score={score})",
    "curator.needs_revision": "Review: NEEDS REVISION (score={score})",
    "curator.rejected": "Review: REJECTED (score={score})",
    "curator.flagged": "Review: FLAGGED for human review",
    "curator.reviewing": "Reviewing output...",

    # ── Security ────────────────────────────────────────────────────────
    "security.permission.denied": "Permission denied: {resource} ({level})",
    "security.permission.granted": "Permission granted: {resource}",
    "security.secret.detected": "Potential secret detected and redacted",
    "security.command.blocked": "Command blocked by sandbox: {command}",
    "security.audit.logged": "Security event logged: {event}",

    # ── Errors ──────────────────────────────────────────────────────────
    "error.general": "An error occurred: {message}",
    "error.timeout": "Operation timed out after {seconds}s",
    "error.rate_limited": "Rate limit exceeded. Try again later.",
    "error.not_found": "{resource} not found",
    "error.validation": "Validation error: {details}",
    "error.connection": "Connection error: {details}",
    "error.auth": "Authentication failed: {details}",
    "error.permission": "Permission denied: {details}",
    "error.internal": "Internal error: {message}",

    # ── CLI ──────────────────────────────────────────────────────────────
    "cli.help": "Type 'help' for available commands",
    "cli.unknown_command": "Unknown command: {command}",
    "cli.confirm_exit": "Exit JARVIS?",
    "cli.prompt": "jarvis> ",
    "cli.processing": "Processing...",
    "cli.done": "Done.",

    # ── Notifications ───────────────────────────────────────────────────
    "notification.sent": "Notification sent: {title}",
    "notification.quiet_hours": "Notification suppressed (quiet hours)",
    "notification.rate_limited": "Notification rate limited",
    "notification.channel.not_found": "Notification channel '{channel}' not found",

    # ── Diagnostics ─────────────────────────────────────────────────────
    "diagnostics.running": "Running system diagnostics...",
    "diagnostics.completed": "Diagnostics completed: {status}",
    "diagnostics.check.passed": "{name}: PASSED",
    "diagnostics.check.failed": "{name}: FAILED",

    # ── Benchmarks ──────────────────────────────────────────────────────
    "benchmark.running": "Running benchmarks ({iterations} iterations)...",
    "benchmark.completed": "Benchmarks completed: {count} tests",
    "benchmark.result": "{name}: {ops_per_sec} ops/s (avg={avg_ms}ms)",

    # ── MCP ──────────────────────────────────────────────────────────────
    "mcp.server.started": "MCP server started on {host}:{port}",
    "mcp.server.stopped": "MCP server stopped",
    "mcp.tool.called": "MCP tool called: {name}",
    "mcp.resource.accessed": "MCP resource accessed: {uri}",

    # ── Workflow ─────────────────────────────────────────────────────────
    "workflow.started": "Workflow started: {name}",
    "workflow.completed": "Workflow completed: {name}",
    "workflow.failed": "Workflow failed: {name} ({error})",
    "workflow.step.started": "Workflow step started: {step}",
    "workflow.step.completed": "Workflow step completed: {step}",
}
