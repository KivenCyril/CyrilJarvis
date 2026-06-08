# JARVIS Security Documentation

This document describes the security architecture, threat model, and best practices for deploying JARVIS safely.

---

## Table of Contents

1. [Threat Model](#threat-model)
2. [Permission System](#permission-system)
3. [Sandbox Modes](#sandbox-modes)
4. [Secret Management](#secret-management)
5. [Audit Logging](#audit-logging)
6. [Agent Security](#agent-security)
7. [Network Security](#network-security)
8. [Security Best Practices](#security-best-practices)

---

## Threat Model

JARVIS is an AI assistant that executes code, accesses the filesystem, makes network requests, and interacts with external services. The primary threat vectors are:

### 1. Malicious LLM Output

**Threat:** The LLM generates dangerous tool calls (e.g., deleting files, exfiltrating data).

**Mitigations:**
- Sandbox modes with command blocklists and allowlists
- File path restrictions (blocked paths, allowed paths)
- Execution time limits
- File size limits

### 2. Prompt Injection

**Threat:** User input or external data manipulates the LLM into performing unintended actions.

**Mitigations:**
- `InputValidationMiddleware` strips control characters and enforces length limits
- System prompts clearly delineate user input from instructions
- Constraints in Streaming Specs act as guardrails
- Curator review catches unsafe outputs

### 3. Secret Leakage

**Threat:** API keys, passwords, or tokens appear in agent output, logs, or UI.

**Mitigations:**
- `SecurityManager.scan_for_secrets()` detects common secret patterns
- `SecurityManager.redact_secrets()` replaces secrets with `[REDACTED]`
- `SecurityMiddleware` in the agent middleware chain sanitizes all output
- `.env` file is excluded from version control via `.gitignore`

### 4. Unauthorized Access

**Threat:** Unauthorized users access the API or admin functions.

**Mitigations:**
- Permission system with hierarchical levels (none < read < write < execute < admin)
- `AuthContext` tracks user identity and permissions per request
- API authentication should be added before production deployment (not enforced by default)

### 5. Resource Exhaustion

**Threat:** Runaway tool execution consumes excessive CPU, memory, or disk.

**Mitigations:**
- Execution time limits (default: 300 seconds per tool call)
- File size limits (default: 100 MB)
- Rate limiting at the Gateway level (30 messages per 60-second window)
- Agent rate limiting via `RateLimitMiddleware`
- `max_concurrent` agent setting (default: 5)

---

## Permission System

### Overview

The permission system (`src/jarvis/security/permissions.py`) implements a hierarchical RBAC-like model.

### Permission Levels

| Level | Value | Description |
|-------|-------|-------------|
| `NONE` | 0 | No access |
| `READ` | 1 | Read-only access |
| `WRITE` | 2 | Read and write access |
| `EXECUTE` | 3 | Read, write, and execute (run tools, commands) |
| `ADMIN` | 4 | Full access (all operations, manage permissions) |

Higher levels implicitly include all lower levels. A `WRITE` permission on `filesystem` grants both `READ` and `WRITE`.

### Permission Model

```python
Permission(
    resource="filesystem",          # what is being accessed
    level=PermissionLevel.WRITE,    # access level
    scope="/tmp/*",                 # path/pattern restriction
    granted_by="system",            # who granted this permission
    granted_at=datetime.now(),      # when it was granted
    expires_at=None,                # optional expiry
)
```

### Resources

| Resource | Description | Typical Level |
|----------|-------------|---------------|
| `filesystem` | File read/write operations | READ or WRITE |
| `shell` | Shell command execution | EXECUTE |
| `network` | HTTP requests, DNS lookups | READ |
| `llm` | LLM API calls | EXECUTE |
| `*` | All resources (wildcard) | Used for admin |

### AuthContext

Every request carries an `AuthContext`:

```python
AuthContext(
    user_id="alice",
    session_id="sess_123",
    permissions=[
        Permission(resource="filesystem", level=PermissionLevel.READ),
        Permission(resource="filesystem", level=PermissionLevel.WRITE, scope="/tmp/*"),
        Permission(resource="shell", level=PermissionLevel.EXECUTE),
        Permission(resource="llm", level=PermissionLevel.EXECUTE),
        Permission(resource="network", level=PermissionLevel.READ),
    ],
    is_admin=False,
    channel="web",
)
```

Admin users (`is_admin=True`) bypass all permission checks.

### Default Permissions

The `AuthContext.default()` factory creates a context with:
- Filesystem read (global)
- Filesystem write (`/tmp/*` only)
- Shell execute
- LLM execute
- Network read

---

## Sandbox Modes

The sandbox system (`src/jarvis/security/sandbox.py`) controls what agents can do at the system level.

### Mode Comparison

| Mode | Shell Commands | File Access | Network | Use Case |
|------|---------------|-------------|---------|----------|
| `none` | All allowed | All allowed | Allowed | Development, trusted environment |
| `basic` | Blocklist enforced | Blocked paths enforced | Allowed | Default, general use |
| `strict` | Allowlist only | Blocked paths + allowed paths | Configurable | Production, untrusted input |
| `docker` | Runs in container | Container filesystem only | Container network | Maximum isolation |

### Command Blocklist (Basic Mode)

The following commands are blocked by default:

```
rm -rf /           rm -rf /*          rm -rf ~
mkfs               dd if=/dev/zero    :(){ :|:& };:
chmod -R 777 /     > /dev/sda         shutdown
reboot             init 0             init 6
```

### Path Restrictions

**Blocked paths** (access denied):
```
/etc/passwd
/etc/shadow
~/.ssh
```

**Allowed paths** (default):
```
/tmp
.  (current directory)
```

### Sandbox Configuration

```python
SandboxConfig(
    mode=SandboxMode.BASIC,
    allowed_commands=[],              # empty = allow all (except blocklist)
    blocked_commands=["rm -rf /", ...],
    allowed_paths=["/tmp", "."],
    blocked_paths=["/etc/passwd", ...],
    max_file_size_mb=100,
    max_execution_time_seconds=300,
    network_allowed=True,
    docker_image="python:3.12-slim",  # for docker mode
)
```

### Validation API

```python
validator = SandboxValidator(config)

# Validate a command
ok, reason = validator.validate_command("ls -la /tmp")
# ok=True, reason=""

ok, reason = validator.validate_command("rm -rf /")
# ok=False, reason="Command blocked: matches pattern 'rm -rf /'"

# Validate file path
ok, reason = validator.validate_file_path("/etc/shadow", write=True)
# ok=False, reason="Path blocked: /etc/shadow"

# Validate network access
ok, reason = validator.validate_network("https://api.example.com")
# ok=True, reason=""
```

---

## Secret Management

### Secret Detection Patterns

The `SecurityManager` (`src/jarvis/security/manager.py`) scans text for:

| Pattern | Matches |
|---------|---------|
| `api_key=...` | Generic API keys (20+ chars) |
| `secret=...`, `token=...`, `password=...` | Generic secrets (8+ chars) |
| `Bearer ...` | Bearer tokens |
| `sk-...` | OpenAI API keys |
| `ghp_...` | GitHub personal access tokens |
| `-----BEGIN PRIVATE KEY-----` | RSA/EC private keys |

### Scanning and Redaction

```python
manager = SecurityManager()

# Scan for secrets
findings = manager.scan_for_secrets("My API key is sk-abc123def456")
# ["Potential secret detected: pattern 'sk-[a-zA-Z0-9]{20,...'"]

# Redact secrets
clean = manager.redact_secrets("My API key is sk-abc123def456")
# "My API key is [REDACTED]"
```

### Environment Variable Security

- API keys should be set via environment variables, not hardcoded
- The `.env` file is listed in `.gitignore` to prevent accidental commits
- In Docker, pass secrets via environment variables or Docker secrets

---

## Audit Logging

### What is Logged

Every permission check is recorded in the audit log:

```python
{
    "action": "permission_check",
    "user": "alice",
    "resource": "filesystem",
    "level": "write",
    "allowed": true,
    "timestamp": "2026-06-02T10:00:00+00:00"
}
```

### Audit API

```python
manager = SecurityManager()

# Check permission (automatically logged)
allowed = manager.check_permission(auth_context, "shell", PermissionLevel.EXECUTE)

# Retrieve audit log
log = manager.get_audit_log(limit=100)
```

### Structured Logging

The `src/jarvis/logging/` module provides:
- `structured.py` -- JSON-formatted structured logging
- `audit.py` -- dedicated audit log with security event tracking

Enable JSON logging for production:

```bash
JARVIS_LOG_FORMAT=json
```

---

## Agent Security

### Middleware-Based Security

The `SecurityMiddleware` (`src/jarvis/agents/middleware.py`) provides agent-level security:

```python
SecurityMiddleware(
    allowed_agents={"code-agent", "data-agent"},  # None = all allowed
    blocked_patterns=[
        r"(?:password|passwd|pwd)\s*[=:]\s*\S+",
        r"(?:api[_-]?key|apikey)\s*[=:]\s*\S+",
        r"(?:secret|token)\s*[=:]\s*\S+",
        r"AKIA[0-9A-Z]{16}",                      # AWS access keys
        r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----",
    ],
)
```

**Before execution:**
- Checks if the agent is in the allowed set
- Raises `PermissionError` if not

**After execution:**
- Scans agent output for blocked patterns
- Replaces matches with `[REDACTED]`
- Logs warnings when redaction occurs

### Input Validation

The `InputValidationMiddleware` sanitizes all input:
- Rejects empty or whitespace-only messages
- Enforces maximum message length (default: 50,000 characters)
- Strips non-printable control characters (except `\n`, `\r`, `\t`)

### Rate Limiting

The `RateLimitMiddleware` uses a sliding window algorithm:
- Default: 10 calls per 60-second window per agent
- Raises `RateLimitError` with `retry_after_seconds` when exceeded

---

## Network Security

### CORS

CORS is configured in `src/jarvis/server/app.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],              # RESTRICT THIS IN PRODUCTION
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

For production, restrict `allow_origins` to your domain in `jarvis.yaml`:

```yaml
server:
  cors_origins:
    - "https://your-domain.com"
```

### WebSocket Security

WebSocket connections at `/ws/specs/{spec_id}` accept a `client_id` query parameter for identification. In production:
- Add authentication before the WebSocket handshake
- Validate `client_id` against authenticated sessions
- The spec must exist or the connection is closed with code 4004

### Rate Limiting

The Gateway enforces per-sender rate limiting:
- 30 messages per 60-second sliding window
- Applied uniformly across all channels
- Exceeding the limit returns an error without processing

---

## Security Best Practices

### Development

1. Use `JARVIS_SANDBOX_MODE=basic` (the default)
2. Keep `.env` file local and never commit it
3. Use the `MockProvider` to avoid leaking real API keys in test logs
4. Run `make lint` to catch common security issues

### Staging

1. Set `JARVIS_SANDBOX_MODE=strict`
2. Configure the `allowed_commands` list explicitly
3. Restrict `cors_origins` to staging domain
4. Enable structured logging (`JARVIS_LOG_FORMAT=json`) for log aggregation
5. Review audit logs regularly

### Production

1. Set `JARVIS_SANDBOX_MODE=strict` or `docker`
2. Add API authentication middleware (API key, OAuth2, or JWT)
3. Restrict CORS to production domain only
4. Enable secret scanning (`JARVIS_SECRET_SCANNING=true`)
5. Deploy behind a reverse proxy with TLS
6. Use Docker secrets or a vault for API keys (not environment variables in plain text)
7. Set up alerting on audit log anomalies (repeated permission denials, secret detections)
8. Rotate API keys regularly
9. Monitor the `/metrics` endpoint for unusual activity patterns
10. Back up audit logs for compliance

### Incident Response

If a secret is leaked in agent output:
1. Rotate the compromised credential immediately
2. Check the audit log for the time window of the leak
3. Review the agent's execution trace (`/traces/{trace_id}`)
4. Add the secret pattern to the `SecurityManager._secret_patterns` list if not already covered
5. Consider adding the agent's input to a blocklist if it was a prompt injection attack
