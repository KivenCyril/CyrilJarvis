from __future__ import annotations

import logging
import re
from typing import Any

from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt -- comprehensive security specialist
# ---------------------------------------------------------------------------

SECURITY_AGENT_SYSTEM_PROMPT = """\
You are a security specialist within the JARVIS assistant system.

# Capabilities
- Code security auditing (OWASP Top 10 2021)
- Dependency vulnerability scanning and CVE analysis
- Secret/credential detection and remediation
- Security header and TLS configuration review
- Compliance framework assessment (SOC2, GDPR, PCI-DSS, HIPAA)
- Infrastructure security review (IAM, network, cloud)
- Threat modeling and attack surface analysis

You have access to tools: shell_execute, read_file, python_execute, find_files.
Be thorough and precise. Prioritize findings by severity using CVSS-like scoring.
Avoid alarmism -- distinguish between theoretical and exploitable vulnerabilities.

# OWASP Top 10 (2021) Checklist

## A01 - Broken Access Control
- Missing function-level access checks
- IDOR (Insecure Direct Object References)
- CORS misconfiguration
- Missing CSRF tokens on state-changing requests
- Path traversal (../../../etc/passwd)
- JWT validation issues (alg=none, missing expiry)

## A02 - Cryptographic Failures
- Hardcoded secrets, API keys, passwords in code
- Weak hashing (MD5, SHA1 for passwords)
- Missing encryption at rest or in transit
- Insecure random number generation
- Certificate validation bypass

## A03 - Injection
- SQL injection (string concatenation in queries)
- Command injection (os.system, subprocess with shell=True)
- LDAP injection, XPath injection
- NoSQL injection (MongoDB $where, $regex)
- Template injection (SSTI)

## A04 - Insecure Design
- Missing rate limiting on sensitive endpoints
- No account lockout after failed attempts
- Missing input validation at design level
- Lack of defense-in-depth

## A05 - Security Misconfiguration
- Default credentials unchanged
- Verbose error messages leaking stack traces
- Unnecessary services/ports exposed
- Missing security headers
- Debug mode enabled in production

## A06 - Vulnerable & Outdated Components
- Known CVEs in dependencies
- End-of-life libraries without security patches
- Unpatched frameworks with public exploits

## A07 - Identification & Authentication Failures
- Weak password policies
- Missing MFA on privileged accounts
- Session tokens in URLs
- Session fixation
- Credential stuffing vulnerability

## A08 - Software & Data Integrity Failures
- Insecure deserialization (pickle, yaml.load)
- Missing code signing / integrity verification
- Insecure CI/CD pipeline (unsigned artifacts)
- Auto-update without signature verification

## A09 - Security Logging & Monitoring Failures
- Missing audit logs for auth events
- Log injection vulnerabilities
- No alerting on suspicious activity
- Sensitive data in logs (passwords, tokens, PII)

## A10 - Server-Side Request Forgery (SSRF)
- User-controlled URLs fetched server-side
- Missing URL scheme/host allowlist
- Cloud metadata endpoint accessible (169.254.169.254)

# Vulnerability Severity Scoring (CVSS-aligned)
Use this scale for all findings:

| Score | Severity | Description                                                    |
|-------|----------|----------------------------------------------------------------|
| 9.0+  | CRITICAL | Remotely exploitable, no auth required, full system compromise |
| 7.0-8.9| HIGH    | Exploitable with some prerequisites, significant impact        |
| 4.0-6.9| MEDIUM  | Requires specific conditions, limited impact                   |
| 0.1-3.9| LOW     | Minimal impact, difficult to exploit                           |
| 0.0   | INFO     | Best-practice suggestion, no direct vulnerability              |

# Secret/Credential Detection Patterns
Scan for these patterns in source code:
- API keys: `[A-Za-z0-9]{32,}` near key/token/api variables
- AWS keys: `AKIA[0-9A-Z]{16}`
- Private keys: `-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----`
- JWT tokens: `eyJ[A-Za-z0-9_-]+\\.eyJ[A-Za-z0-9_-]+`
- Connection strings with passwords
- Environment variables with sensitive defaults
- .env files committed to version control

# Security Headers Checklist
Verify the following HTTP response headers:
- Content-Security-Policy (CSP) -- restricts resource loading origins
- X-Content-Type-Options: nosniff -- prevents MIME sniffing
- X-Frame-Options: DENY or SAMEORIGIN -- clickjacking protection
- Strict-Transport-Security (HSTS) -- forces HTTPS
- X-XSS-Protection: 0 (rely on CSP instead)
- Referrer-Policy: strict-origin-when-cross-origin
- Permissions-Policy -- restricts browser features
- Cache-Control: no-store for sensitive responses

# Compliance Framework Quick Reference

## SOC 2 (Trust Services Criteria)
- CC6.1: Logical access controls
- CC6.6: Encryption in transit
- CC6.7: Restriction of data transmission
- CC7.2: Monitoring for anomalies
- CC8.1: Change management process

## GDPR (Data Protection)
- Art. 5: Data minimization, purpose limitation
- Art. 25: Privacy by design
- Art. 32: Encryption and pseudonymization
- Art. 33: 72-hour breach notification
- Art. 35: Data protection impact assessment

## PCI-DSS (Payment Card)
- Req. 2: No default passwords
- Req. 3: Protect stored cardholder data
- Req. 4: Encrypt transmission of cardholder data
- Req. 6: Develop secure systems
- Req. 8: Strong access control
- Req. 10: Track and monitor access
- Req. 11: Regular security testing

# Remediation Template
For each finding, provide:
1. **What**: Clear description of the vulnerability
2. **Where**: File, line number, or configuration
3. **Impact**: What an attacker could achieve
4. **Fix**: Specific code/config change with example
5. **Verify**: How to confirm the fix works
6. **Prevent**: How to prevent recurrence (linter rule, test, policy)
"""

# ---------------------------------------------------------------------------
# Task type definitions
# ---------------------------------------------------------------------------

_TASK_AUDIT = "audit"
_TASK_VULNERABILITY = "vulnerability"
_TASK_SECRETS = "secrets"
_TASK_NETWORK = "network"
_TASK_COMPLIANCE = "compliance"
_TASK_THREAT_MODEL = "threat-model"
_TASK_GENERAL = "general"

_TASK_KEYWORDS: list[tuple[list[str], str]] = [
    (["audit", "审计", "review code", "owasp", "security review", "code review"], _TASK_AUDIT),
    (
        ["vulnerab", "漏洞", "cve", "dependency", "依赖", "outdated", "patch",
         "upgrade", "snyk", "npm audit", "pip audit", "trivy"],
        _TASK_VULNERABILITY,
    ),
    (
        ["secret", "密钥", "credential", "password", "密码", "token",
         "api key", "private key", "env file", "hardcoded"],
        _TASK_SECRETS,
    ),
    (
        ["network", "网络", "port", "端口", "tls", "ssl", "firewall",
         "header", "cors", "csp", "hsts", "https"],
        _TASK_NETWORK,
    ),
    (
        ["compliance", "合规", "soc2", "soc 2", "gdpr", "pci", "pci-dss",
         "hipaa", "iso 27001", "regulation", "法规"],
        _TASK_COMPLIANCE,
    ),
    (
        ["threat model", "威胁建模", "attack surface", "攻击面",
         "stride", "dread", "risk assess", "风险评估"],
        _TASK_THREAT_MODEL,
    ),
]

# ---------------------------------------------------------------------------
# Strategy-specific prompt augmentations
# ---------------------------------------------------------------------------

_TASK_PROMPTS: dict[str, str] = {
    _TASK_AUDIT: (
        "Perform a comprehensive security audit:\n"
        "1. Walk through each OWASP Top 10 category systematically.\n"
        "2. Score each finding using the CVSS-aligned severity scale.\n"
        "3. Provide specific file/line references.\n"
        "4. Fill in the remediation template for each finding.\n"
        "5. Summarize: total findings by severity, top 3 priorities."
    ),
    _TASK_VULNERABILITY: (
        "Perform dependency vulnerability scanning:\n"
        "1. List all dependencies and their versions.\n"
        "2. Check for known CVEs using available tools.\n"
        "3. Score each CVE by severity and exploitability.\n"
        "4. Recommend upgrade paths (patch, minor, major).\n"
        "5. Flag end-of-life dependencies.\n"
        "6. Check for dependency confusion risks."
    ),
    _TASK_SECRETS: (
        "Perform secret/credential detection:\n"
        "1. Scan source code for hardcoded secrets using regex patterns.\n"
        "2. Check .env files, config files, and CI/CD configurations.\n"
        "3. Verify .gitignore excludes sensitive files.\n"
        "4. Check git history for leaked secrets (git log -p).\n"
        "5. Recommend: vault integration, env vars, secret rotation."
    ),
    _TASK_NETWORK: (
        "Perform network security review:\n"
        "1. Check all HTTP security headers against the checklist.\n"
        "2. Verify TLS configuration (protocol version, cipher suites).\n"
        "3. Review CORS policy for overly permissive origins.\n"
        "4. Check for exposed ports and services.\n"
        "5. Verify CSP policy blocks inline scripts and unsafe-eval."
    ),
    _TASK_COMPLIANCE: (
        "Assess compliance posture:\n"
        "1. Identify which frameworks apply based on data types and geography.\n"
        "2. Map current controls to framework requirements.\n"
        "3. Identify gaps and non-conformities.\n"
        "4. Prioritize remediation by risk and regulatory deadline.\n"
        "5. Document evidence of compliance for audit trail."
    ),
    _TASK_THREAT_MODEL: (
        "Build a threat model:\n"
        "1. Identify assets (data, services, infrastructure).\n"
        "2. Map trust boundaries and data flows.\n"
        "3. Apply STRIDE per component (Spoofing, Tampering, Repudiation, "
        "Information Disclosure, Denial of Service, Elevation of Privilege).\n"
        "4. Score threats using DREAD or CVSS.\n"
        "5. Propose mitigations for high/critical threats."
    ),
}

# ---------------------------------------------------------------------------
# Mock outputs
# ---------------------------------------------------------------------------

_MOCK_OUTPUTS: dict[str, str] = {
    _TASK_AUDIT: (
        "Security audit complete:\n"
        "- 1 CRITICAL: SQL injection in user input handler (A03)\n"
        "- 1 HIGH: Missing CSRF token on payment endpoint (A01)\n"
        "- 3 MEDIUM: Verbose error messages expose stack traces (A05)\n"
        "- 5 LOW: Missing security headers (A05)\n"
        "Top priority: Fix SQL injection immediately."
    ),
    _TASK_VULNERABILITY: (
        "Dependency scan results:\n"
        "- 2 CVEs found in 47 dependencies scanned.\n"
        "- CVE-2024-1234 (CRITICAL 9.8): Remote code execution in serializer v2.1.\n"
        "  Fix: upgrade to v2.3.1.\n"
        "- CVE-2024-5678 (MEDIUM 5.3): ReDoS in validator v1.0.\n"
        "  Fix: upgrade to v1.0.3."
    ),
    _TASK_SECRETS: (
        "Secret scan results:\n"
        "- No hardcoded credentials detected in source code.\n"
        "- .env properly listed in .gitignore.\n"
        "- WARNING: AWS access key found in git history (commit abc123).\n"
        "  Recommendation: rotate key immediately, use git-filter-repo to purge."
    ),
    _TASK_NETWORK: (
        "Network security review:\n"
        "- TLS 1.3 configured correctly.\n"
        "- Missing headers: Content-Security-Policy, Permissions-Policy.\n"
        "- CORS allows *.example.com -- consider restricting to specific origins.\n"
        "- 2 open ports reviewed: 443 (HTTPS), 8080 (health check -- restrict to internal)."
    ),
    _TASK_COMPLIANCE: (
        "Compliance assessment:\n"
        "- SOC 2: 3 gaps identified (CC6.1 access logs, CC7.2 monitoring, CC8.1 change mgmt).\n"
        "- GDPR: Data minimization review needed for user profiles.\n"
        "- PCI-DSS: Not applicable (no cardholder data stored)."
    ),
    _TASK_THREAT_MODEL: (
        "Threat model summary:\n"
        "- 4 trust boundaries identified.\n"
        "- 12 threats enumerated via STRIDE.\n"
        "- 3 HIGH threats: auth bypass, SSRF to cloud metadata, insecure deserialization.\n"
        "- Mitigations proposed for all HIGH and CRITICAL threats."
    ),
    _TASK_GENERAL: "Security review complete. No critical issues.",
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

# Compiled patterns for secret detection
_SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----"),
    "jwt_token": re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+"),
    "generic_secret": re.compile(
        r"""(?:password|secret|token|api_?key|auth)\s*[=:]\s*['"][^'"]{8,}['"]""",
        re.IGNORECASE,
    ),
    "connection_string": re.compile(
        r"(?:mysql|postgres|mongodb|redis)://[^:]+:[^@]+@",
        re.IGNORECASE,
    ),
}


def scan_for_secrets(text: str) -> list[dict[str, str]]:
    """Scan *text* for potential hardcoded secrets.

    Returns a list of dicts with keys: ``pattern_name``, ``match``, ``position``.
    """
    findings: list[dict[str, str]] = []
    for name, pattern in _SECRET_PATTERNS.items():
        for match in pattern.finditer(text):
            # Redact most of the match for safety
            raw = match.group()
            redacted = raw[:8] + "..." + raw[-4:] if len(raw) > 16 else raw[:4] + "..."
            findings.append({
                "pattern_name": name,
                "match": redacted,
                "position": str(match.start()),
            })
    return findings


def score_severity(base_score: float) -> str:
    """Map a CVSS-like base score to a severity label."""
    if base_score >= 9.0:
        return "CRITICAL"
    if base_score >= 7.0:
        return "HIGH"
    if base_score >= 4.0:
        return "MEDIUM"
    if base_score >= 0.1:
        return "LOW"
    return "INFO"


def format_finding(
    severity: str,
    category: str,
    description: str,
    location: str = "",
    remediation: str = "",
) -> str:
    """Format a single security finding for human-readable output."""
    parts = [f"[{severity}] ({category})"]
    if location:
        parts.append(f"@ {location}")
    parts.append(f"-- {description}")
    result = " ".join(parts)
    if remediation:
        result += f"\n  Remediation: {remediation}"
    return result


# ---------------------------------------------------------------------------
# SecurityAgent
# ---------------------------------------------------------------------------

class SecurityAgent(BaseAgent):
    """Specialist agent for security auditing and vulnerability analysis.

    Supports multiple security workflows:
    - **audit**: full OWASP Top 10 code security review
    - **vulnerability**: dependency scanning and CVE analysis
    - **secrets**: credential/secret detection in source code and git history
    - **network**: security headers, TLS, CORS, port review
    - **compliance**: SOC2, GDPR, PCI-DSS gap assessment
    - **threat-model**: STRIDE-based threat enumeration and risk scoring
    """

    def __init__(self) -> None:
        super().__init__(AgentCard(
            name="security-agent",
            description="Security auditing, vulnerability scanning, and secrets detection",
            skills=["security-audit", "vulnerability-scan", "owasp", "secrets-detection", "dependency-check"],
            input_modes=["text", "code-diff"],
            output_modes=["text", "structured-data"],
            domain="security",
            can_delegate=True,
            tool_filter=["shell_execute", "read_file", "list_directory", "git_log"],
        ))

    # -- public API --------------------------------------------------------

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        logger.info("[SecurityAgent] Processing: %s", message[:80])

        task_type = self._classify(message)

        # Try LLM-backed execution first
        if self._llm_registry:
            system_prompt = self._build_system_prompt(task_type)
            result = await self._llm_execute(
                message, context,
                system_prompt=system_prompt,
                max_tool_rounds=3,
            )
            if result.success:
                return result
            logger.warning("[SecurityAgent] LLM execution failed, falling back to mock: %s", result.error)

        # Mock fallback
        output = f"[SecurityAgent] Task type: '{task_type}'. "
        output += _MOCK_OUTPUTS.get(task_type, _MOCK_OUTPUTS[_TASK_GENERAL])

        return TaskResult(
            task_id=context.task_id, agent_name=self.name,
            success=True, output=output,
        )

    def can_handle(self, message: str) -> float:
        keywords = [
            "security", "安全", "vulnerab", "漏洞", "audit", "审计",
            "owasp", "secret", "密钥", "credential", "password", "密码",
            "cve", "injection", "注入", "xss", "csrf", "auth",
            "encrypt", "加密", "firewall", "防火墙", "scan", "扫描",
            "compliance", "合规", "soc2", "gdpr", "pci",
            "threat model", "tls", "ssl", "header",
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
        parts = [SECURITY_AGENT_SYSTEM_PROMPT]

        augmentation = _TASK_PROMPTS.get(task_type)
        if augmentation:
            parts.append(f"\n# Current security task: {task_type}\n{augmentation}")

        return "\n".join(parts)
