"""Network operation tools: ping, DNS lookup, and port check."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


class PingTool(BaseTool):
    """Ping a host and return latency statistics."""

    name = "ping"
    description = (
        "Ping a host to check connectivity and measure round-trip latency. "
        "Returns packet loss and min/avg/max latency statistics."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "host": {
                "type": "string",
                "description": "Hostname or IP address to ping.",
            },
            "count": {
                "type": "integer",
                "description": "Number of ping packets to send (default 3).",
                "default": 3,
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds for the entire ping operation (default 10).",
                "default": 10,
            },
        },
        "required": ["host"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        host: str = arguments["host"]
        count: int = arguments.get("count", 3)
        timeout: int = arguments.get("timeout", 10)

        # Basic validation
        if not host or len(host) > 253:
            return ToolResult(success=False, output="Invalid host")

        try:
            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", str(count), host,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            return ToolResult(success=False, output=f"Ping timed out after {timeout}s")
        except OSError as exc:
            return ToolResult(success=False, output=f"Failed to run ping: {exc}")

        raw = stdout.decode(errors="replace")

        if proc.returncode != 0:
            return ToolResult(
                success=True,
                output=f"Host {host} is unreachable\n{raw}",
                data={"host": host, "reachable": False},
            )

        # Parse statistics
        stats: dict[str, Any] = {"host": host, "reachable": True}

        # Packet loss
        loss_match = re.search(r"(\d+(?:\.\d+)?)% packet loss", raw)
        if loss_match:
            stats["packet_loss"] = float(loss_match.group(1))

        # Latency: min/avg/max/stddev
        lat_match = re.search(
            r"(?:rtt|round-trip)\s+min/avg/max/(?:std-?dev|mdev)\s*=\s*"
            r"([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)",
            raw,
        )
        if lat_match:
            stats["min_ms"] = float(lat_match.group(1))
            stats["avg_ms"] = float(lat_match.group(2))
            stats["max_ms"] = float(lat_match.group(3))
            stats["stddev_ms"] = float(lat_match.group(4))

        summary_parts = [f"Host: {host} — reachable"]
        if "avg_ms" in stats:
            summary_parts.append(
                f"Latency: {stats['min_ms']}/{stats['avg_ms']}/{stats['max_ms']} ms (min/avg/max)"
            )
        if "packet_loss" in stats:
            summary_parts.append(f"Packet loss: {stats['packet_loss']}%")

        return ToolResult(
            success=True,
            output="\n".join(summary_parts),
            data=stats,
        )


class DNSLookupTool(BaseTool):
    """Perform DNS lookup for a domain."""

    name = "dns_lookup"
    description = (
        "Perform a DNS lookup for a domain name and return the resolved records. "
        "Supports A, AAAA, MX, TXT, CNAME, and NS record types."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "description": "Domain name to look up.",
            },
            "record_type": {
                "type": "string",
                "enum": ["A", "AAAA", "MX", "TXT", "CNAME", "NS"],
                "description": "DNS record type (default: A).",
                "default": "A",
            },
        },
        "required": ["domain"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        domain: str = arguments["domain"]
        record_type: str = arguments.get("record_type", "A")

        try:
            proc = await asyncio.create_subprocess_exec(
                "dig", "+short", domain, record_type,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        except FileNotFoundError:
            # Fall back to nslookup
            try:
                proc = await asyncio.create_subprocess_exec(
                    "nslookup", f"-type={record_type}", domain,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            except asyncio.TimeoutError:
                return ToolResult(success=False, output="DNS lookup timed out")
            except OSError as exc:
                return ToolResult(success=False, output=f"Failed to run DNS lookup: {exc}")
        except asyncio.TimeoutError:
            return ToolResult(success=False, output="DNS lookup timed out")
        except OSError as exc:
            return ToolResult(success=False, output=f"Failed to run dig: {exc}")

        if proc.returncode != 0:
            return ToolResult(
                success=False,
                output=stderr.decode(errors="replace").strip() or "DNS lookup failed",
            )

        raw = stdout.decode(errors="replace").strip()
        if not raw:
            return ToolResult(
                success=True,
                output=f"No {record_type} records found for {domain}",
                data={"domain": domain, "record_type": record_type, "records": []},
            )

        records = [line.strip() for line in raw.splitlines() if line.strip()]
        output = f"DNS {record_type} records for {domain}:\n" + "\n".join(f"  {r}" for r in records)

        return ToolResult(
            success=True,
            output=output,
            data={"domain": domain, "record_type": record_type, "records": records},
        )


class PortCheckTool(BaseTool):
    """Check if a TCP port is open on a host."""

    name = "port_check"
    description = (
        "Check if a specific TCP port is open on a host by attempting "
        "to establish a connection."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "host": {
                "type": "string",
                "description": "Hostname or IP address.",
            },
            "port": {
                "type": "integer",
                "description": "Port number to check (1-65535).",
            },
            "timeout": {
                "type": "number",
                "description": "Connection timeout in seconds (default 3).",
                "default": 3,
            },
        },
        "required": ["host", "port"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        host: str = arguments["host"]
        port: int = arguments["port"]
        timeout: float = arguments.get("timeout", 3)

        if not (1 <= port <= 65535):
            return ToolResult(success=False, output=f"Invalid port number: {port}")

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout,
            )
            writer.close()
            await writer.wait_closed()

            return ToolResult(
                success=True,
                output=f"Port {port} on {host} is OPEN",
                data={"host": host, "port": port, "open": True},
            )
        except asyncio.TimeoutError:
            return ToolResult(
                success=True,
                output=f"Port {port} on {host} is CLOSED (connection timed out)",
                data={"host": host, "port": port, "open": False},
            )
        except ConnectionRefusedError:
            return ToolResult(
                success=True,
                output=f"Port {port} on {host} is CLOSED (connection refused)",
                data={"host": host, "port": port, "open": False},
            )
        except OSError as exc:
            return ToolResult(
                success=True,
                output=f"Port {port} on {host} is CLOSED ({exc})",
                data={"host": host, "port": port, "open": False},
            )
