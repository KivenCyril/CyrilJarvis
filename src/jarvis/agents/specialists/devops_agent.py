from __future__ import annotations

import logging
from typing import Any

from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt -- comprehensive DevOps specialist
# ---------------------------------------------------------------------------

DEVOPS_AGENT_SYSTEM_PROMPT = """\
You are a DevOps specialist within the JARVIS assistant system.

# Capabilities
- Docker container management and Dockerfile authoring
- Kubernetes operations (deployments, services, troubleshooting, scaling)
- CI/CD pipeline creation and management (GitHub Actions, GitLab CI, Jenkins)
- Infrastructure as Code (Terraform, Ansible, Pulumi, CloudFormation)
- Monitoring, alerting, and observability setup
- Deployment strategies (blue-green, canary, rolling, A/B)

You have access to tools: shell_execute, read_file, write_file, http_request.
Focus on automation, reliability, and infrastructure-as-code best practices.

# Docker Best Practices Checklist

## Dockerfile
- [ ] Use specific base image tags (not :latest)
- [ ] Use multi-stage builds to minimize image size
- [ ] Order layers for optimal cache utilization (least-changing first)
- [ ] Run as non-root user (USER directive)
- [ ] Use COPY instead of ADD (unless extracting archives)
- [ ] Minimize layer count by combining RUN commands
- [ ] Use .dockerignore to exclude unnecessary files
- [ ] Set HEALTHCHECK instruction
- [ ] Use LABEL for metadata (maintainer, version)
- [ ] Pin package versions in apt-get/apk install

## Security
- [ ] Scan images for vulnerabilities (trivy, snyk)
- [ ] No secrets in image layers
- [ ] Read-only root filesystem where possible
- [ ] Drop all capabilities, add only needed ones
- [ ] Use distroless or alpine base images for production

## Docker Compose
- [ ] Use named volumes for persistent data
- [ ] Set resource limits (memory, CPU)
- [ ] Define health checks for all services
- [ ] Use env_file instead of inline environment variables
- [ ] Network isolation between services

# Kubernetes Resource Templates

## Deployment best practices
- Set resource requests AND limits for all containers
- Use liveness, readiness, and startup probes
- Set pod disruption budgets (PDB) for HA
- Use pod anti-affinity for spreading across nodes
- Configure HPA (Horizontal Pod Autoscaler) for auto-scaling
- Use rolling update strategy with maxSurge and maxUnavailable
- Set terminationGracePeriodSeconds appropriately

## Service best practices
- Use ClusterIP for internal services
- Use LoadBalancer or Ingress for external access
- Set appropriate session affinity if needed
- Use NetworkPolicies to restrict traffic

## Security
- Use RBAC with least-privilege
- Enable PodSecurityStandards (restricted profile)
- Mount service account tokens only when needed
- Use Secrets (or external secret manager) for sensitive config
- Scan manifests with kube-bench, kubesec, or OPA

## Namespaces & Organization
- Separate environments (dev, staging, prod) by namespace
- Apply ResourceQuotas per namespace
- Use LimitRanges for default resource constraints
- Label everything: app, version, environment, team

# CI/CD Pipeline Patterns

## GitHub Actions
```yaml
# Standard pipeline structure
on: [push, pull_request]
jobs:
  lint:          # Static analysis
  test:          # Unit + integration tests
  build:         # Build artifacts / images
  security:      # Dependency + image scanning
  deploy-staging: # Auto-deploy to staging
    needs: [lint, test, build, security]
  deploy-prod:   # Manual approval + deploy
    needs: [deploy-staging]
    environment: production
```

## GitLab CI
```yaml
stages:
  - validate
  - test
  - build
  - security
  - deploy
# Use rules: for conditional execution
# Use cache: for dependency caching
# Use artifacts: for build outputs
# Use needs: for DAG pipelines
```

## Pipeline best practices
- [ ] Fail fast: lint and unit tests first
- [ ] Cache dependencies (node_modules, .m2, pip cache)
- [ ] Use matrix builds for multi-version testing
- [ ] Pin action/runner versions
- [ ] Store secrets in CI/CD secret management
- [ ] Use branch protection rules for production
- [ ] Implement automatic rollback on deploy failure
- [ ] Add deployment notifications (Slack, email)

# Infrastructure as Code

## Terraform best practices
- Use remote state (S3 + DynamoDB, Terraform Cloud)
- Lock state to prevent concurrent modifications
- Use modules for reusable components
- Separate environments using workspaces or directory structure
- Tag all resources consistently
- Use data sources to reference existing infrastructure
- Run `terraform plan` in CI, `terraform apply` only after approval
- Use `terraform validate` and `tflint` in CI

## Ansible best practices
- Use roles for modular, reusable configuration
- Use ansible-vault for secrets
- Make playbooks idempotent
- Use handlers for service restarts
- Tag tasks for selective execution
- Test with molecule

# Monitoring & Alerting

## Observability stack
- **Metrics**: Prometheus + Grafana (or Datadog, CloudWatch)
- **Logs**: ELK/EFK stack, Loki, or cloud-native logging
- **Traces**: Jaeger, Zipkin, or OpenTelemetry
- **Dashboards**: Grafana with SLI/SLO tracking

## Key metrics to monitor
- **RED method** (request-oriented):
  - Rate: requests per second
  - Errors: error rate / ratio
  - Duration: latency percentiles (p50, p95, p99)
- **USE method** (resource-oriented):
  - Utilization: % of resource used
  - Saturation: work queued
  - Errors: error events
- **Golden signals**: latency, traffic, errors, saturation

## Alerting best practices
- Alert on symptoms, not causes
- Use severity levels (critical, warning, info)
- Include runbooks in alert descriptions
- Set appropriate thresholds to avoid alert fatigue
- Page only for customer-impacting issues
- Use escalation policies

# Deployment Strategies

## Blue-Green
- Two identical environments (blue and green)
- Route traffic to new version atomically
- Instant rollback by switching back
- Requires 2x resources during deploy
- Best for: critical services needing instant rollback

## Canary
- Route small % of traffic to new version
- Gradually increase if metrics are healthy
- Automatic rollback if error rate exceeds threshold
- Best for: services with large user base

## Rolling Update
- Replace instances one by one (or in batches)
- Zero-downtime if instances are stateless
- Slower rollback (must roll forward or back)
- Default Kubernetes strategy

## A/B Testing
- Route traffic based on user attributes
- Compare metrics between versions
- Best for: feature experimentation
"""

# ---------------------------------------------------------------------------
# Task type definitions
# ---------------------------------------------------------------------------

_TASK_DOCKER = "docker"
_TASK_KUBERNETES = "kubernetes"
_TASK_CICD = "ci-cd"
_TASK_TERRAFORM = "terraform"
_TASK_MONITORING = "monitoring"
_TASK_DEPLOYMENT = "deployment"
_TASK_GENERAL = "general"

_TASK_KEYWORDS: list[tuple[list[str], str]] = [
    (
        ["docker", "container", "容器", "dockerfile", "image", "镜像",
         "compose", "registry", "ecr", "gcr", "dockerhub"],
        _TASK_DOCKER,
    ),
    (
        ["k8s", "kubernetes", "kubectl", "pod", "deployment", "helm",
         "service", "ingress", "namespace", "configmap", "secret",
         "hpa", "pdb", "daemonset", "statefulset", "operator"],
        _TASK_KUBERNETES,
    ),
    (
        ["ci/cd", "ci-cd", "pipeline", "流水线", "github action", "jenkins",
         "gitlab ci", "circleci", "travis", "workflow", "build automation",
         "continuous integration", "continuous delivery", "continuous deployment"],
        _TASK_CICD,
    ),
    (
        ["terraform", "ansible", "infra", "基础设施", "iac", "pulumi",
         "cloudformation", "cdk", "infrastructure as code",
         "provision", "cloud", "aws", "gcp", "azure"],
        _TASK_TERRAFORM,
    ),
    (
        ["monitor", "监控", "prometheus", "grafana", "metric", "指标",
         "dashboard", "alert", "告警", "log", "日志", "trace", "链路追踪",
         "observability", "可观测", "elk", "loki", "datadog", "slo", "sli"],
        _TASK_MONITORING,
    ),
    (
        ["deploy", "部署", "release", "发布", "rollout", "上线",
         "blue-green", "canary", "金丝雀", "rolling", "rollback", "回滚",
         "strategy", "策略"],
        _TASK_DEPLOYMENT,
    ),
]

# ---------------------------------------------------------------------------
# Strategy-specific prompt augmentations
# ---------------------------------------------------------------------------

_TASK_PROMPTS: dict[str, str] = {
    _TASK_DOCKER: (
        "Working with Docker:\n"
        "1. Review/create Dockerfile using the best practices checklist.\n"
        "2. Use multi-stage builds for production images.\n"
        "3. Scan for security vulnerabilities.\n"
        "4. Optimize layer caching and image size.\n"
        "5. Test with docker build and docker run.\n"
        "6. Set up .dockerignore for build context."
    ),
    _TASK_KUBERNETES: (
        "Working with Kubernetes:\n"
        "1. Define resources with proper requests and limits.\n"
        "2. Configure health probes (liveness, readiness, startup).\n"
        "3. Set up HPA for auto-scaling.\n"
        "4. Apply security best practices (RBAC, PodSecurity).\n"
        "5. Use labels and annotations consistently.\n"
        "6. Test with kubectl apply --dry-run=client."
    ),
    _TASK_CICD: (
        "Working with CI/CD:\n"
        "1. Structure pipeline: lint -> test -> build -> security -> deploy.\n"
        "2. Cache dependencies for faster builds.\n"
        "3. Use matrix builds for multi-version testing.\n"
        "4. Set up environment-specific deployment stages.\n"
        "5. Add deployment notifications and rollback triggers.\n"
        "6. Store secrets securely in CI/CD secret management."
    ),
    _TASK_TERRAFORM: (
        "Working with Infrastructure as Code:\n"
        "1. Use modules for reusable components.\n"
        "2. Configure remote state with locking.\n"
        "3. Separate environments properly.\n"
        "4. Tag all resources consistently.\n"
        "5. Run plan in CI, apply only after review.\n"
        "6. Use tflint and terraform validate in CI."
    ),
    _TASK_MONITORING: (
        "Setting up monitoring and alerting:\n"
        "1. Identify key metrics using RED and USE methods.\n"
        "2. Set up Prometheus scraping / metric collection.\n"
        "3. Create Grafana dashboards with SLI/SLO tracking.\n"
        "4. Configure alerts with proper severity and thresholds.\n"
        "5. Write runbooks for each alert.\n"
        "6. Set up log aggregation and search."
    ),
    _TASK_DEPLOYMENT: (
        "Managing deployments:\n"
        "1. Choose the right strategy based on requirements.\n"
        "2. Define health checks and success criteria.\n"
        "3. Set up automatic rollback triggers.\n"
        "4. Configure gradual traffic shifting (for canary/A-B).\n"
        "5. Test rollback procedure.\n"
        "6. Send deployment notifications."
    ),
}

# ---------------------------------------------------------------------------
# Mock outputs
# ---------------------------------------------------------------------------

_MOCK_OUTPUTS: dict[str, str] = {
    _TASK_DOCKER: (
        "Dockerfile optimized:\n"
        "- Multi-stage build: build stage (golang:1.22) + runtime stage (gcr.io/distroless/static).\n"
        "- Image size reduced from 1.2GB to 18MB.\n"
        "- Non-root user configured.\n"
        "- Health check added.\n"
        "- No vulnerabilities found (trivy scan clean)."
    ),
    _TASK_KUBERNETES: (
        "K8s deployment configured:\n"
        "- 3 replicas with rolling update strategy.\n"
        "- Resource limits: 256Mi memory, 250m CPU.\n"
        "- HPA: min 3, max 10, target CPU 70%.\n"
        "- Liveness/readiness probes on /healthz.\n"
        "- PDB: minAvailable 2."
    ),
    _TASK_CICD: (
        "CI/CD pipeline created:\n"
        "- Stages: lint -> test -> build -> security-scan -> deploy.\n"
        "- Dependency caching configured (3x faster builds).\n"
        "- Auto-deploy to staging on push to main.\n"
        "- Manual approval gate for production.\n"
        "- Slack notifications on deploy status."
    ),
    _TASK_TERRAFORM: (
        "Terraform configuration generated:\n"
        "- 3 resources to create, 0 to destroy.\n"
        "- Remote state configured with S3 + DynamoDB locking.\n"
        "- Variables extracted to variables.tf.\n"
        "- Outputs defined for downstream consumers.\n"
        "- tflint: 0 issues."
    ),
    _TASK_MONITORING: (
        "Monitoring setup complete:\n"
        "- Prometheus scraping configured for all services.\n"
        "- Grafana dashboard with RED metrics (latency p50/p95/p99, error rate, RPS).\n"
        "- Alerts: >1% error rate (warning), >5% (critical).\n"
        "- Latency: >500ms p95 (warning), >1s (critical).\n"
        "- Runbooks linked in alert annotations."
    ),
    _TASK_DEPLOYMENT: (
        "Deployment strategy configured:\n"
        "- Canary deployment: 5% -> 25% -> 50% -> 100%.\n"
        "- Auto-rollback if error rate > 1% during canary.\n"
        "- Health check validation at each step.\n"
        "- Estimated deployment time: 15 minutes.\n"
        "- Rollback time: <30 seconds."
    ),
    _TASK_GENERAL: "Infrastructure task processed.",
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def generate_dockerfile(
    base_image: str = "python:3.12-slim",
    app_dir: str = "/app",
    port: int = 8000,
    entrypoint: str = "python -m app",
    multi_stage: bool = True,
) -> str:
    """Generate a best-practice Dockerfile template."""
    lines: list[str] = []

    if multi_stage:
        lines.extend([
            f"# -- Build stage --",
            f"FROM {base_image} AS builder",
            f"WORKDIR {app_dir}",
            "",
            "# Install dependencies first for layer caching",
            "COPY requirements.txt .",
            "RUN pip install --no-cache-dir --user -r requirements.txt",
            "",
            "COPY . .",
            "",
            "# -- Runtime stage --",
            f"FROM {base_image}",
        ])
    else:
        lines.extend([
            f"FROM {base_image}",
        ])

    lines.extend([
        "",
        f"WORKDIR {app_dir}",
        "",
        "# Create non-root user",
        "RUN addgroup --system app && adduser --system --ingroup app app",
        "",
    ])

    if multi_stage:
        lines.extend([
            "# Copy installed packages and app from builder",
            "COPY --from=builder /root/.local /home/app/.local",
            f"COPY --from=builder {app_dir} {app_dir}",
            "",
            "ENV PATH=/home/app/.local/bin:$PATH",
            "",
        ])
    else:
        lines.extend([
            "COPY requirements.txt .",
            "RUN pip install --no-cache-dir -r requirements.txt",
            "",
            "COPY . .",
            "",
        ])

    lines.extend([
        f"EXPOSE {port}",
        "",
        f"HEALTHCHECK --interval=30s --timeout=5s --retries=3 \\",
        f"  CMD curl -f http://localhost:{port}/healthz || exit 1",
        "",
        "USER app",
        "",
        f'ENTRYPOINT ["{entrypoint.split()[0]}"]',
    ])
    if len(entrypoint.split()) > 1:
        args = ", ".join(f'"{a}"' for a in entrypoint.split()[1:])
        lines.append(f"CMD [{args}]")

    return "\n".join(lines)


def generate_github_actions_pipeline(
    language: str = "python",
    deploy_env: str = "production",
) -> str:
    """Generate a GitHub Actions CI/CD pipeline template."""
    return f"""\
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up {language}
        uses: actions/setup-{language}@v5
      - name: Lint
        run: echo "Add lint command here"

  test:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - name: Set up {language}
        uses: actions/setup-{language}@v5
      - name: Test
        run: echo "Add test command here"

  build:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - name: Build
        run: echo "Add build command here"

  deploy-staging:
    runs-on: ubuntu-latest
    needs: build
    if: github.ref == 'refs/heads/main'
    environment: staging
    steps:
      - name: Deploy to staging
        run: echo "Add staging deploy here"

  deploy-{deploy_env}:
    runs-on: ubuntu-latest
    needs: deploy-staging
    if: github.ref == 'refs/heads/main'
    environment: {deploy_env}
    steps:
      - name: Deploy to {deploy_env}
        run: echo "Add prod deploy here"
"""


def generate_k8s_deployment(
    name: str = "app",
    image: str = "app:latest",
    replicas: int = 3,
    port: int = 8000,
    memory_limit: str = "256Mi",
    cpu_limit: str = "500m",
) -> str:
    """Generate a Kubernetes deployment manifest following best practices."""
    return f"""\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}
  labels:
    app: {name}
spec:
  replicas: {replicas}
  selector:
    matchLabels:
      app: {name}
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: {name}
    spec:
      containers:
        - name: {name}
          image: {image}
          ports:
            - containerPort: {port}
          resources:
            requests:
              memory: "128Mi"
              cpu: "100m"
            limits:
              memory: "{memory_limit}"
              cpu: "{cpu_limit}"
          livenessProbe:
            httpGet:
              path: /healthz
              port: {port}
            initialDelaySeconds: 15
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /ready
              port: {port}
            initialDelaySeconds: 5
            periodSeconds: 5
          startupProbe:
            httpGet:
              path: /healthz
              port: {port}
            failureThreshold: 30
            periodSeconds: 2
---
apiVersion: v1
kind: Service
metadata:
  name: {name}
spec:
  selector:
    app: {name}
  ports:
    - port: 80
      targetPort: {port}
  type: ClusterIP
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {name}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {name}
  minReplicas: {replicas}
  maxReplicas: {replicas * 3}
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
"""


# ---------------------------------------------------------------------------
# DevOpsAgent
# ---------------------------------------------------------------------------

class DevOpsAgent(BaseAgent):
    """Specialist agent for DevOps and infrastructure tasks.

    Supports multiple infrastructure workflows:
    - **docker**: Dockerfile authoring, image optimization, security scanning
    - **kubernetes**: resource manifests, deployment, scaling, troubleshooting
    - **ci-cd**: pipeline creation for GitHub Actions, GitLab CI, Jenkins
    - **terraform**: Infrastructure as Code with Terraform, Ansible, Pulumi
    - **monitoring**: observability setup with Prometheus, Grafana, alerting
    - **deployment**: strategy selection (blue-green, canary, rolling)
    """

    def __init__(self) -> None:
        super().__init__(AgentCard(
            name="devops-agent",
            description="Docker, Kubernetes, CI/CD pipelines, and infrastructure as code",
            skills=["docker", "kubernetes", "ci-cd", "terraform", "ansible", "monitoring"],
            input_modes=["text", "structured-data"],
            output_modes=["text", "code", "structured-data"],
            domain="devops",
            can_delegate=True,
        ))

    # -- public API --------------------------------------------------------

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        logger.info("[DevOpsAgent] Processing: %s", message[:80])

        task_type = self._classify(message)

        # Try LLM-backed execution first
        if self._llm_registry:
            system_prompt = self._build_system_prompt(task_type)
            result = await self._llm_execute(
                message, context,
                system_prompt=system_prompt,
                max_tool_rounds=8,
            )
            if result.success:
                return result
            logger.warning("[DevOpsAgent] LLM execution failed, falling back to mock: %s", result.error)

        # Mock fallback
        output = f"[DevOpsAgent] Task type: '{task_type}'. "
        output += _MOCK_OUTPUTS.get(task_type, _MOCK_OUTPUTS[_TASK_GENERAL])

        return TaskResult(
            task_id=context.task_id, agent_name=self.name,
            success=True, output=output,
        )

    def can_handle(self, message: str) -> float:
        keywords = [
            "docker", "容器", "kubernetes", "k8s", "ci/cd", "ci-cd",
            "pipeline", "流水线", "terraform", "ansible", "infra",
            "基础设施", "deploy", "部署", "container", "image", "镜像",
            "helm", "prometheus", "grafana", "jenkins", "github action",
            "yaml", "dockerfile", "compose", "nginx",
            "monitoring", "observability", "alerting",
            "canary", "blue-green", "rollback",
        ]
        msg = message.lower()
        hits = sum(1 for k in keywords if k in msg)
        return min(hits * 0.25, 1.0)

    # -- private helpers ---------------------------------------------------

    def _classify(self, message: str) -> str:
        msg = message.lower()
        for keywords, category in _TASK_KEYWORDS:
            if any(k in msg for k in keywords):
                return category
        return _TASK_GENERAL

    def _build_system_prompt(self, task_type: str) -> str:
        """Compose a task-specific system prompt."""
        parts = [DEVOPS_AGENT_SYSTEM_PROMPT]

        augmentation = _TASK_PROMPTS.get(task_type)
        if augmentation:
            parts.append(f"\n# Current DevOps task: {task_type}\n{augmentation}")

        return "\n".join(parts)
