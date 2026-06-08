#!/usr/bin/env python3
"""security_demo.py -- Security system demonstration.

Shows JARVIS's security features: permission system, sandbox
validation, secret scanning and redaction, and audit logging.

Run:
    python examples/security_demo.py
"""

from __future__ import annotations

import asyncio
import sys

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
except ImportError:
    print("ERROR: `rich` is required.  pip install rich")
    sys.exit(1)

try:
    from jarvis.security.manager import SecurityManager
    from jarvis.security.permissions import AuthContext, Permission, PermissionLevel
    from jarvis.security.sandbox import SandboxConfig, SandboxMode, SandboxValidator
except ImportError as exc:
    print(f"ERROR: Cannot import jarvis modules: {exc}")
    sys.exit(1)

console = Console()


async def main() -> None:
    console.print(Panel("[bold cyan]JARVIS -- Security Demo[/bold cyan]",
                        subtitle="Permissions, Sandbox, Secret Scanning"))

    # -------------------------------------------------------------------
    # 1. Permission system
    # -------------------------------------------------------------------
    console.print("\n[bold]1. Permission system:[/bold]")

    # Create a default auth context
    ctx = AuthContext.default()
    console.print(f"   User: {ctx.user_id}")
    console.print(f"   Admin: {ctx.is_admin}")
    console.print(f"   Permissions: {len(ctx.permissions)}")

    security = SecurityManager()

    # Check various permissions
    checks = [
        ("filesystem", PermissionLevel.READ),
        ("filesystem", PermissionLevel.WRITE),
        ("filesystem", PermissionLevel.ADMIN),
        ("shell", PermissionLevel.EXECUTE),
        ("network", PermissionLevel.READ),
        ("network", PermissionLevel.WRITE),
        ("llm", PermissionLevel.EXECUTE),
        ("database", PermissionLevel.WRITE),
    ]

    table = Table(title="Permission Checks")
    table.add_column("Resource", style="cyan")
    table.add_column("Level", style="yellow")
    table.add_column("Allowed", style="bold")

    for resource, level in checks:
        allowed = security.check_permission(ctx, resource, level)
        style = "green" if allowed else "red"
        table.add_row(resource, level.value, f"[{style}]{allowed}[/{style}]")
    console.print(table)

    # Admin context
    console.print("\n   Admin context (bypasses all checks):")
    admin_ctx = AuthContext(user_id="admin", is_admin=True)
    allowed = security.check_permission(admin_ctx, "database", PermissionLevel.ADMIN)
    console.print(f"   database/admin: [green]{allowed}[/green]")

    # Custom permissions
    console.print("\n   Custom permission context:")
    custom_ctx = AuthContext(
        user_id="developer",
        permissions=[
            Permission(resource="filesystem", level=PermissionLevel.WRITE),
            Permission(resource="docker", level=PermissionLevel.EXECUTE),
        ],
    )
    console.print(f"   filesystem/write: {security.check_permission(custom_ctx, 'filesystem', PermissionLevel.WRITE)}")
    console.print(f"   docker/execute: {security.check_permission(custom_ctx, 'docker', PermissionLevel.EXECUTE)}")
    console.print(f"   shell/execute: {security.check_permission(custom_ctx, 'shell', PermissionLevel.EXECUTE)}")

    # -------------------------------------------------------------------
    # 2. Sandbox validation
    # -------------------------------------------------------------------
    console.print("\n[bold]2. Sandbox validation:[/bold]")

    # Basic mode
    sandbox = SandboxValidator(SandboxConfig(mode=SandboxMode.BASIC))
    console.print(f"   Mode: {sandbox.config.mode.value}")

    commands = [
        "ls -la",
        "python3 script.py",
        "rm -rf /",
        "cat /etc/passwd",
        "docker ps",
        "rm -rf /*",
        "chmod -R 777 /",
        ":(){ :|:& };:",
    ]

    table = Table(title="Command Validation (BASIC mode)")
    table.add_column("Command", style="cyan")
    table.add_column("Allowed", style="bold")
    table.add_column("Reason")

    for cmd in commands:
        allowed, reason = sandbox.validate_command(cmd)
        style = "green" if allowed else "red"
        table.add_row(cmd, f"[{style}]{allowed}[/{style}]", reason or "-")
    console.print(table)

    # Strict mode
    console.print("\n   Strict mode (allowlist-based):")
    strict_sandbox = SandboxValidator(SandboxConfig(
        mode=SandboxMode.STRICT,
        allowed_commands=["ls", "cat", "python3", "echo"],
    ))
    strict_cmds = ["ls -la", "python3 app.py", "rm file.txt", "curl http://example.com"]
    for cmd in strict_cmds:
        allowed, reason = strict_sandbox.validate_command(cmd)
        style = "green" if allowed else "red"
        console.print(f"   [{style}]{'OK' if allowed else 'BLOCKED'}[/{style}] {cmd}  {reason}")

    # File path validation
    console.print("\n   File path validation:")
    paths = ["/tmp/data.txt", "/etc/shadow", "~/.ssh/id_rsa", "./project/main.py"]
    for path in paths:
        allowed, reason = sandbox.validate_file_path(path, write=True)
        style = "green" if allowed else "red"
        console.print(f"   [{style}]{'OK' if allowed else 'BLOCKED'}[/{style}] {path}  {reason}")

    # -------------------------------------------------------------------
    # 3. Secret scanning and redaction
    # -------------------------------------------------------------------
    console.print("\n[bold]3. Secret scanning and redaction:[/bold]")

    texts_with_secrets = [
        "My API key is api_key=sk-abcdefghijklmnopqrstuvwxyz123456",
        "Use token: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc",
        "GitHub token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij",
        "password=MySecurePassword123!",
        "No secrets in this text at all.",
        "The connection string uses host=localhost:5432",
    ]

    for text in texts_with_secrets:
        findings = security.scan_for_secrets(text)
        if findings:
            console.print(f"   [red]SECRET FOUND[/red] in: '{text[:60]}...'")
            for finding in findings:
                console.print(f"     - {finding}")
            redacted = security.redact_secrets(text)
            console.print(f"     Redacted: '{redacted[:60]}...'")
        else:
            console.print(f"   [green]CLEAN[/green] '{text[:60]}'")

    # -------------------------------------------------------------------
    # 4. Audit logging
    # -------------------------------------------------------------------
    console.print("\n[bold]4. Audit log:[/bold]")
    audit_log = security.get_audit_log()

    table = Table(title=f"Audit Log ({len(audit_log)} entries)")
    table.add_column("Action", style="cyan")
    table.add_column("User", style="yellow")
    table.add_column("Resource")
    table.add_column("Level")
    table.add_column("Allowed", style="bold")

    for entry in audit_log[:10]:
        allowed = entry.get("allowed", False)
        style = "green" if allowed else "red"
        table.add_row(
            entry.get("action", ""),
            entry.get("user", ""),
            entry.get("resource", ""),
            entry.get("level", ""),
            f"[{style}]{allowed}[/{style}]",
        )
    console.print(table)

    console.print("\n[bold green]Demo complete![/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
