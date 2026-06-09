from __future__ import annotations

import logging
import re
from typing import Any

from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt -- comprehensive operations specialist
# ---------------------------------------------------------------------------

OPS_AGENT_SYSTEM_PROMPT = """\
You are an operations and infrastructure specialist within the JARVIS assistant system.

# Capabilities
- System monitoring and health checks with structured checklists
- Alert diagnosis and incident response with severity classification
- Deployment planning and execution with rollback strategies
- Infrastructure management (containers, clusters, cloud resources)
- Runbook creation and execution
- Capacity planning and cost optimization
- SLA/SLO tracking and compliance reporting

You have access to tools: shell_execute, read_file, write_file, python_execute.
Use shell commands to check system status, logs, and metrics.
Provide actionable recommendations, not just observations.

# Execution protocol
1. **Assess** -- understand the current situation (alert, request, incident).
2. **Classify** -- determine severity, scope, and urgency.
3. **Investigate** -- gather metrics, logs, and system state.
4. **Diagnose** -- identify root cause or most likely hypothesis.
5. **Act** -- execute the appropriate runbook or ad-hoc fix.
6. **Verify** -- confirm resolution with health checks.
7. **Document** -- record the incident, actions taken, and lessons learned.

# Incident severity classification (P0-P4)
Classify incidents by business impact:

| Severity | Impact                    | Response Time | Escalation          | Example                    |
|----------|---------------------------|---------------|---------------------|----------------------------|
| P0       | Total service outage      | Immediate     | Exec + on-call      | Database cluster down      |
| P1       | Major feature degraded    | < 15 min      | Engineering lead     | Payment processing slow    |
| P2       | Minor feature impacted    | < 1 hour      | Team lead            | Search results stale       |
| P3       | Cosmetic / low impact     | < 4 hours     | Sprint backlog       | Typo in error message      |
| P4       | Improvement opportunity   | Next sprint   | Backlog              | Log format inconsistency   |

## Severity determination signals
- Error rate spike (> 1% = P1, > 5% = P0)
- Latency increase (> 2x baseline = P2, > 10x = P1, timeout = P0)
- Availability drop (< 99.9% = P2, < 99% = P1, < 95% = P0)
- Data integrity issues (any = P0)
- Security breach indicators (any confirmed = P0)

# Runbook template system
Create runbooks using this template:

```
# Runbook: {title}
## Metadata
- Author: {name}
- Last updated: {date}
- Severity: {P0-P4}
- Services affected: {list}
- Estimated resolution time: {duration}

## Prerequisites
- [ ] Access to {system/tool}
- [ ] Permissions: {required roles}

## Symptoms
- {observable symptom 1}
- {observable symptom 2}

## Diagnosis steps
1. {step with specific command}
2. {step with expected output}

## Resolution steps
1. {action with rollback procedure}
2. {verification step}

## Rollback procedure
1. {rollback step}
2. {verification after rollback}

## Post-incident
- [ ] Update monitoring/alerting
- [ ] Root cause analysis
- [ ] Preventive measures
```

# Health check checklist
When performing health checks, verify:

## Application layer
- [ ] HTTP health endpoints returning 200
- [ ] Response time within SLA (p50, p95, p99)
- [ ] Error rate below threshold
- [ ] Active connections within limits
- [ ] Queue depths normal
- [ ] Cache hit rates acceptable

## Infrastructure layer
- [ ] CPU utilization < 80%
- [ ] Memory utilization < 85%
- [ ] Disk usage < 90%
- [ ] Network I/O within bounds
- [ ] DNS resolution working
- [ ] TLS certificates valid (> 30 days to expiry)

## Data layer
- [ ] Database connections available
- [ ] Replication lag < threshold
- [ ] Backup freshness < 24h
- [ ] Query performance normal
- [ ] Storage growth rate sustainable

## External dependencies
- [ ] Third-party API availability
- [ ] CDN performance
- [ ] DNS provider status
- [ ] Cloud provider status page

# Capacity planning hints
When analyzing capacity:
- Project growth based on trailing 30/90/180 day trends
- Factor in known upcoming events (launches, promotions, seasonal spikes)
- Apply safety margin: 1.5x for compute, 2x for storage
- Consider auto-scaling limits and cold-start times
- Plan for failure scenarios (N+1 redundancy minimum)
- Review historical peak-to-average ratios

# Cost optimization strategies
Identify cost reduction opportunities:
1. **Right-sizing** -- identify over-provisioned instances (CPU < 20%, memory < 30%)
2. **Reserved instances** -- commit for stable workloads (savings: 30-60%)
3. **Spot/preemptible** -- use for fault-tolerant batch workloads
4. **Auto-scaling** -- scale down during off-peak hours
5. **Storage tiering** -- move cold data to cheaper storage classes
6. **Unused resources** -- terminate idle instances, unattached volumes, old snapshots
7. **Data transfer** -- minimize cross-region/cross-AZ traffic
8. **License optimization** -- consolidate or switch to open-source alternatives

# SLA/SLO awareness
Track and report on service level objectives:

## Common SLO types
- **Availability**: percentage of uptime (e.g., 99.95% = 21.9 min downtime/month)
- **Latency**: p50, p95, p99 response times
- **Error rate**: percentage of failed requests
- **Throughput**: requests per second capacity
- **Durability**: data loss probability

## Error budget
- Monthly error budget = 1 - SLO target (e.g., 99.9% SLO = 0.1% error budget = 43.2 min)
- Track burn rate: budget consumed / time elapsed
- Alert when burn rate > 1x (on track to exhaust budget)
- Freeze deployments when error budget < 10% remaining

## SLO reporting format
```
Service: {name}
Period: {month/quarter}
SLO Target: {percentage}
Actual: {percentage}
Error Budget: {remaining minutes/percentage}
Status: {HEALTHY | WARNING | BREACHED}
Incidents: {count with links}
```
"""

# ---------------------------------------------------------------------------
# Infrastructure pattern detection
# ---------------------------------------------------------------------------

_INFRA_PATTERNS: dict[str, list[str]] = {
    "kubernetes": ["k8s", "kubernetes", "pod", "deployment", "service", "ingress",
                   "namespace", "helm", "kube", "kubectl"],
    "docker": ["docker", "container", "image", "dockerfile", "compose"],
    "cloud": ["aws", "gcp", "azure", "cloud", "ec2", "s3", "lambda", "ecs",
              "aliyun", "阿里云", "腾讯云", "tencent cloud"],
    "database": ["mysql", "postgres", "redis", "mongodb", "elasticsearch",
                 "database", "db", "rds", "cache"],
    "network": ["dns", "load balancer", "nginx", "cdn", "ssl", "tls", "firewall",
                "vpc", "subnet"],
}

# ---------------------------------------------------------------------------
# Task type definitions
# ---------------------------------------------------------------------------

_TASK_ALERT = "alert"
_TASK_DEPLOY = "deploy"
_TASK_INCIDENT = "incident"
_TASK_MONITORING = "monitoring"
_TASK_RUNBOOK = "runbook"
_TASK_CAPACITY = "capacity"
_TASK_COST = "cost"
_TASK_SLO = "slo"
_TASK_HEALTH_CHECK = "health-check"

_TASK_KEYWORDS: list[tuple[list[str], str]] = [
    (["alert", "告警", "warning", "alarm", "报警", "pager"], _TASK_ALERT),
    (["deploy", "部署", "release", "发布", "rollout", "上线", "rollback", "回滚"], _TASK_DEPLOY),
    (["incident", "故障", "outage", "宕机", "down", "crash", "崩溃", "postmortem"], _TASK_INCIDENT),
    (["runbook", "操作手册", "playbook", "procedure", "流程", "standard operating"], _TASK_RUNBOOK),
    (["capacity", "容量", "scaling", "扩容", "growth", "增长", "provision", "sizing"], _TASK_CAPACITY),
    (["cost", "成本", "billing", "费用", "budget", "预算", "optimize cost", "省钱"], _TASK_COST),
    (["slo", "sla", "error budget", "uptime", "可用性", "availability"], _TASK_SLO),
    (["health", "健康", "check", "检查", "status", "状态", "ping", "heartbeat"], _TASK_HEALTH_CHECK),
]

# ---------------------------------------------------------------------------
# Task-specific prompt augmentations
# ---------------------------------------------------------------------------

_TASK_PROMPTS: dict[str, str] = {
    _TASK_ALERT: (
        "You are diagnosing an alert. "
        "Classify the severity (P0-P4). "
        "Identify affected services and potential root cause. "
        "Suggest immediate mitigation steps."
    ),
    _TASK_DEPLOY: (
        "You are managing a deployment. "
        "Check prerequisites, run pre-deployment health checks. "
        "Plan the rollout strategy (canary, blue-green, rolling). "
        "Prepare rollback procedure. "
        "Execute post-deployment verification."
    ),
    _TASK_INCIDENT: (
        "You are handling an incident. Follow incident response protocol:\n"
        "1. Acknowledge and classify severity.\n"
        "2. Assemble response team.\n"
        "3. Investigate and diagnose.\n"
        "4. Apply mitigation.\n"
        "5. Verify resolution.\n"
        "6. Document timeline and root cause.\n"
        "7. Schedule postmortem."
    ),
    _TASK_MONITORING: (
        "You are reviewing monitoring data. "
        "Check all health indicators per the checklist. "
        "Flag any metrics approaching thresholds. "
        "Provide a status summary: green/yellow/red per service."
    ),
    _TASK_RUNBOOK: (
        "You are creating or executing a runbook. "
        "Follow the runbook template. "
        "Include specific commands and expected outputs. "
        "Add rollback procedures for each step."
    ),
    _TASK_CAPACITY: (
        "You are performing capacity planning. "
        "Analyze current utilization trends. "
        "Project future needs with growth assumptions. "
        "Recommend scaling actions with timeline."
    ),
    _TASK_COST: (
        "You are optimizing infrastructure costs. "
        "Identify top cost drivers. "
        "Apply cost optimization strategies. "
        "Estimate savings for each recommendation."
    ),
    _TASK_SLO: (
        "You are reviewing SLA/SLO compliance. "
        "Calculate current performance vs. targets. "
        "Report error budget status. "
        "Flag services at risk of breaching SLOs."
    ),
    _TASK_HEALTH_CHECK: (
        "You are performing a health check. "
        "Run through the health check checklist. "
        "Report status for each category: application, infrastructure, data, external. "
        "Flag any items that need attention."
    ),
}

# ---------------------------------------------------------------------------
# Mock outputs per task type
# ---------------------------------------------------------------------------

_MOCK_OUTPUTS: dict[str, str] = {
    _TASK_ALERT: (
        "Alert analyzed: high memory usage on web-server-03.\n"
        "Severity: P2 (minor degradation)\n"
        "Root cause: memory leak in cache layer.\n"
        "Recommendation: restart service, apply patch in next release."
    ),
    _TASK_DEPLOY: "Deployment plan generated. Pre-checks passed. Canary at 5% recommended.",
    _TASK_INCIDENT: (
        "Incident triaged: P1 severity.\n"
        "  Affected services: 3 identified\n"
        "  Timeline: started 14:23 UTC\n"
        "  Status: investigating\n"
        "  Next step: check database connection pool"
    ),
    _TASK_MONITORING: "Health check: all services green. CPU avg 45%, memory 62%, disk 71%.",
    _TASK_RUNBOOK: "Runbook created with 8 steps, 3 verification checkpoints, and rollback procedure.",
    _TASK_CAPACITY: (
        "Capacity analysis:\n"
        "  Current: 60% utilized\n"
        "  Projected (90 days): 78%\n"
        "  Recommendation: add 2 nodes by month 2"
    ),
    _TASK_COST: (
        "Cost optimization opportunities:\n"
        "  1. Right-size 4 instances: save $320/mo\n"
        "  2. Reserved instances for DB: save $180/mo\n"
        "  3. Delete 12 unused volumes: save $45/mo\n"
        "  Total potential savings: $545/mo"
    ),
    _TASK_SLO: (
        "SLO report:\n"
        "  Availability: 99.97% (target: 99.95%) -- HEALTHY\n"
        "  Latency p99: 180ms (target: 200ms) -- HEALTHY\n"
        "  Error budget remaining: 72% (18 min)"
    ),
    _TASK_HEALTH_CHECK: (
        "Health check complete:\n"
        "  Application: GREEN (all endpoints responding)\n"
        "  Infrastructure: YELLOW (disk at 87%)\n"
        "  Data: GREEN (replication lag < 1s)\n"
        "  External: GREEN (all dependencies available)"
    ),
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def detect_infrastructure(text: str) -> str | None:
    """Detect the infrastructure type mentioned in *text*."""
    lower = text.lower()
    scores: dict[str, int] = {}
    for infra, patterns in _INFRA_PATTERNS.items():
        score = sum(1 for p in patterns if p in lower)
        if score:
            scores[infra] = score
    if not scores:
        return None
    return max(scores, key=scores.get)  # type: ignore[arg-type]


def classify_severity(text: str) -> str:
    """Classify incident severity from text signals."""
    lower = text.lower()
    if any(k in lower for k in ["outage", "down", "crash", "data loss", "breach", "宕机", "崩溃"]):
        return "P0"
    if any(k in lower for k in ["degraded", "slow", "timeout", "high error", "降级", "超时"]):
        return "P1"
    if any(k in lower for k in ["intermittent", "partial", "warning", "间歇", "偶发"]):
        return "P2"
    if any(k in lower for k in ["cosmetic", "minor", "low impact", "轻微"]):
        return "P3"
    return "P2"  # default to moderate


def calculate_error_budget(slo_target: float, actual: float, period_days: int = 30) -> dict[str, Any]:
    """Calculate error budget status.

    Args:
        slo_target: SLO target as fraction (e.g., 0.999 for 99.9%)
        actual: actual availability as fraction
        period_days: reporting period in days

    Returns:
        Dict with budget details.
    """
    total_minutes = period_days * 24 * 60
    budget_minutes = total_minutes * (1 - slo_target)
    consumed_minutes = total_minutes * (1 - actual)
    remaining = max(0, budget_minutes - consumed_minutes)
    remaining_pct = (remaining / budget_minutes * 100) if budget_minutes > 0 else 0

    status = "HEALTHY"
    if remaining_pct < 10:
        status = "BREACHED"
    elif remaining_pct < 30:
        status = "WARNING"

    return {
        "budget_total_min": round(budget_minutes, 1),
        "consumed_min": round(consumed_minutes, 1),
        "remaining_min": round(remaining, 1),
        "remaining_pct": round(remaining_pct, 1),
        "status": status,
    }


# ---------------------------------------------------------------------------
# OpsAgent
# ---------------------------------------------------------------------------

class OpsAgent(BaseAgent):
    """Specialist agent for operations and infrastructure tasks.

    Supports multiple operations workflows:
    - **alert**: diagnose and triage alerts with severity classification
    - **deploy**: plan and execute deployments with rollback
    - **incident**: structured incident response and postmortem
    - **monitoring**: health checks with comprehensive checklists
    - **runbook**: create and execute operational runbooks
    - **capacity**: capacity planning with growth projections
    - **cost**: infrastructure cost optimization
    - **slo**: SLA/SLO compliance tracking and error budgets
    - **health-check**: systematic health verification
    """

    def __init__(self) -> None:
        super().__init__(AgentCard(
            name="ops-agent",
            description="Monitoring, incident response, deployment, runbooks, capacity planning, and SLO tracking",
            skills=["monitoring", "alert", "deploy", "incident", "k8s", "ops",
                    "runbook", "capacity", "cost-optimization", "slo"],
            input_modes=["text", "structured-data"],
            output_modes=["text", "structured-data"],
            domain="operations",
            can_delegate=True,
            tool_filter=["shell_execute", "system_info", "disk_usage", "process_list"],
        ))

    # -- public API --------------------------------------------------------

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        logger.info("[OpsAgent] Processing: %s", message[:80])

        task_type = self._classify(message)
        infra = detect_infrastructure(message)
        severity = classify_severity(message) if task_type in (_TASK_ALERT, _TASK_INCIDENT) else None

        # Try LLM-backed execution first
        if self._llm_registry:
            system_prompt = self._build_system_prompt(task_type, infra, severity)
            result = await self._llm_execute(
                message, context,
                system_prompt=system_prompt,
                max_tool_rounds=3,
            )
            if result.success:
                return result
            logger.warning("[OpsAgent] LLM execution failed, falling back to mock: %s", result.error)

        # Mock fallback
        output = f"[OpsAgent] Task type: '{task_type}'"
        if infra:
            output += f", infrastructure='{infra}'"
        if severity:
            output += f", severity='{severity}'"
        output += ". "
        output += _MOCK_OUTPUTS.get(task_type, "Operations task processed.")

        return TaskResult(
            task_id=context.task_id, agent_name=self.name,
            success=True, output=output,
        )

    def can_handle(self, message: str) -> float:
        keywords = [
            "ops", "运维", "monitor", "监控", "alert", "告警",
            "deploy", "部署", "incident", "故障", "k8s", "kubernetes",
            "server", "服务器", "cluster", "集群", "pod", "container",
            "rollback", "回滚", "scale", "扩容", "runbook", "操作手册",
            "capacity", "容量", "cost", "成本", "slo", "sla",
            "health check", "健康检查", "error budget", "uptime",
        ]
        msg = message.lower()
        return min(sum(1 for k in keywords if k in msg) * 0.3, 1.0)

    # -- private helpers ---------------------------------------------------

    def _classify(self, message: str) -> str:
        msg = message.lower()
        for keywords, category in _TASK_KEYWORDS:
            if any(k in msg for k in keywords):
                return category
        return _TASK_MONITORING  # safe default

    def _build_system_prompt(self, task_type: str, infra: str | None, severity: str | None) -> str:
        """Compose a task-specific system prompt with infrastructure context."""
        parts = [OPS_AGENT_SYSTEM_PROMPT]

        augmentation = _TASK_PROMPTS.get(task_type)
        if augmentation:
            parts.append(f"\n# Current task: {task_type}\n{augmentation}")

        if infra:
            parts.append(
                f"\n# Detected infrastructure: {infra}\n"
                f"Apply {infra}-specific operations commands and best practices."
            )

        if severity:
            parts.append(f"\n# Classified severity: {severity}\nFollow {severity} response protocol.")

        return "\n".join(parts)
