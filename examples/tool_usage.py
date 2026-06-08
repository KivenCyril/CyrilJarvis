#!/usr/bin/env python3
"""tool_usage.py -- Tool system demonstration.

Shows JARVIS's built-in tool registry: listing all tools, executing
shell commands, file operations, calculator, unit conversion, hash
and encoding, git operations, and template rendering.

Run:
    python examples/tool_usage.py
"""

from __future__ import annotations

import asyncio
import sys
import tempfile

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
except ImportError:
    print("ERROR: `rich` is required.  pip install rich")
    sys.exit(1)

try:
    # Import the builtin tools -- this auto-registers them in tool_registry
    from jarvis.tools.builtin import tool_registry
except ImportError as exc:
    print(f"ERROR: Cannot import jarvis modules: {exc}")
    sys.exit(1)

console = Console()


async def main() -> None:
    console.print(Panel("[bold cyan]JARVIS -- Tool Usage Demo[/bold cyan]",
                        subtitle="43 Built-in Tools"))

    # -------------------------------------------------------------------
    # 1. List all registered tools
    # -------------------------------------------------------------------
    console.print("\n[bold]1. All registered tools:[/bold]")
    tools = tool_registry.list_tools()
    console.print(f"   Total tools: {len(tools)}")

    table = Table(title=f"Tool Registry ({len(tools)} tools)")
    table.add_column("#", style="dim", width=3)
    table.add_column("Name", style="cyan")
    table.add_column("Description", max_width=50)

    for i, tool in enumerate(tools, 1):
        desc = tool.description[:50] + "..." if len(tool.description) > 50 else tool.description
        table.add_row(str(i), tool.name, desc)
    console.print(table)

    # -------------------------------------------------------------------
    # 2. Calculator and math
    # -------------------------------------------------------------------
    console.print("\n[bold]2. Calculator tool:[/bold]")
    calc_exprs = ["2 + 3 * 4", "sqrt(144)", "pi * 2.5 ** 2", "log(1000, 10)"]
    for expr in calc_exprs:
        result = await tool_registry.execute("calculator", {"expression": expr})
        status = "[green]OK[/green]" if result.success else "[red]FAIL[/red]"
        console.print(f"   {status} {expr} = {result.output}")

    # -------------------------------------------------------------------
    # 3. Unit conversion
    # -------------------------------------------------------------------
    console.print("\n[bold]3. Unit conversion tool:[/bold]")
    conversions = [
        {"value": 100, "from_unit": "celsius", "to_unit": "fahrenheit"},
        {"value": 1, "from_unit": "mile", "to_unit": "km"},
        {"value": 1024, "from_unit": "MB", "to_unit": "GB"},
    ]
    for conv in conversions:
        result = await tool_registry.execute("unit_convert", conv)
        status = "[green]OK[/green]" if result.success else "[red]FAIL[/red]"
        console.print(f"   {status} {conv['value']} {conv['from_unit']} -> {result.output}")

    # -------------------------------------------------------------------
    # 4. Hash and encoding tools
    # -------------------------------------------------------------------
    console.print("\n[bold]4. Hash and encoding:[/bold]")
    test_string = "Hello, JARVIS!"

    # Base64 encode
    result = await tool_registry.execute("base64", {"action": "encode", "text": test_string})
    console.print(f"   Base64 encode: {result.output}")

    # Hash
    for algo in ["md5", "sha256"]:
        result = await tool_registry.execute("hash", {"text": test_string, "algorithm": algo})
        console.print(f"   {algo}: {result.output[:40]}...")

    # URL encode
    url_text = "hello world & foo=bar"
    result = await tool_registry.execute("url_encode", {"text": url_text, "action": "encode"})
    console.print(f"   URL encode: '{url_text}' -> {result.output}")

    # -------------------------------------------------------------------
    # 5. Date/time operations
    # -------------------------------------------------------------------
    console.print("\n[bold]5. Date/time tools:[/bold]")
    result = await tool_registry.execute("datetime", {"action": "now"})
    console.print(f"   Current time: {result.output}")

    result = await tool_registry.execute("datetime", {
        "action": "format",
        "date": "2024-01-15T10:30:00",
        "format": "%B %d, %Y at %I:%M %p",
    })
    console.print(f"   Formatted: {result.output}")

    # -------------------------------------------------------------------
    # 6. JSON operations
    # -------------------------------------------------------------------
    console.print("\n[bold]6. JSON operations:[/bold]")
    test_json = '{"users": [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]}'
    result = await tool_registry.execute("json_query", {
        "json_text": test_json,
        "query": "users",
    })
    console.print(f"   Query 'users': {result.output[:80]}")

    # -------------------------------------------------------------------
    # 7. Text processing
    # -------------------------------------------------------------------
    console.print("\n[bold]7. Text processing:[/bold]")
    result = await tool_registry.execute("regex", {
        "text": "My email is user@example.com and backup is admin@test.org",
        "pattern": r"[\w.+-]+@[\w-]+\.[\w.]+",
        "action": "findall",
    })
    console.print(f"   Regex findall emails: {result.output}")

    # -------------------------------------------------------------------
    # 8. System info
    # -------------------------------------------------------------------
    console.print("\n[bold]8. System information:[/bold]")
    result = await tool_registry.execute("system_info", {})
    if result.success:
        console.print(f"   {result.output[:200]}...")
    else:
        console.print(f"   [yellow]System info: {result.output}[/yellow]")

    # -------------------------------------------------------------------
    # 9. File operations
    # -------------------------------------------------------------------
    console.print("\n[bold]9. File operations:[/bold]")
    tmpdir = tempfile.mkdtemp(prefix="jarvis_tools_")
    test_file = f"{tmpdir}/test.txt"

    # Write a file
    result = await tool_registry.execute("write_file", {
        "path": test_file,
        "content": "Hello from JARVIS tool system!\nLine 2.\nLine 3.",
    })
    console.print(f"   Write: {result.output}")

    # Read it back
    result = await tool_registry.execute("read_file", {"path": test_file})
    console.print(f"   Read: {result.output[:60]}...")

    # -------------------------------------------------------------------
    # 10. Template rendering
    # -------------------------------------------------------------------
    console.print("\n[bold]10. Template rendering:[/bold]")
    result = await tool_registry.execute("template", {
        "template": "Hello {{name}}, welcome to {{project}}!",
        "variables": {"name": "Developer", "project": "JARVIS"},
    })
    console.print(f"   Rendered: {result.output}")

    # -------------------------------------------------------------------
    # 11. Directory listing
    # -------------------------------------------------------------------
    console.print("\n[bold]11. Directory listing:[/bold]")
    result = await tool_registry.execute("list_directory", {"path": tmpdir})
    console.print(f"   {tmpdir}: {result.output}")

    # -------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------
    console.print(f"\n[bold]Summary:[/bold] {len(tools)} tools available, "
                  f"all working in mock/local mode")

    console.print("\n[bold green]Demo complete![/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
