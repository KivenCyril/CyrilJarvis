"""JWT tools: decode and validate JWT tokens (no cryptographic verification)."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


def _base64url_decode(data: str) -> bytes:
    """Decode base64url-encoded data with padding correction."""
    # Add padding if needed
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data)


def _decode_jwt_parts(token: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Decode a JWT token into header, payload, and signature.

    Returns (header_dict, payload_dict, signature_b64).
    Raises ValueError on invalid structure.
    """
    parts = token.strip().split(".")
    if len(parts) != 3:
        raise ValueError(f"JWT must have 3 parts separated by dots, got {len(parts)}")

    try:
        header_json = _base64url_decode(parts[0])
        header = json.loads(header_json)
    except (json.JSONDecodeError, Exception) as e:
        raise ValueError(f"Invalid JWT header: {e}")

    try:
        payload_json = _base64url_decode(parts[1])
        payload = json.loads(payload_json)
    except (json.JSONDecodeError, Exception) as e:
        raise ValueError(f"Invalid JWT payload: {e}")

    signature = parts[2]

    return header, payload, signature


def _analyze_jwt(header: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Analyze JWT header and payload for common fields."""
    analysis: dict[str, Any] = {}

    # Header analysis
    analysis["algorithm"] = header.get("alg", "unknown")
    analysis["token_type"] = header.get("typ", "unknown")
    if "kid" in header:
        analysis["key_id"] = header["kid"]

    # Time-based fields
    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()

    if "exp" in payload:
        exp_dt = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        analysis["expires_at"] = exp_dt.isoformat()
        analysis["is_expired"] = now_ts > payload["exp"]
        if analysis["is_expired"]:
            analysis["expired_ago"] = str(now - exp_dt)
        else:
            analysis["expires_in"] = str(exp_dt - now)

    if "iat" in payload:
        iat_dt = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
        analysis["issued_at"] = iat_dt.isoformat()

    if "nbf" in payload:
        nbf_dt = datetime.fromtimestamp(payload["nbf"], tz=timezone.utc)
        analysis["not_before"] = nbf_dt.isoformat()
        analysis["is_active"] = now_ts >= payload["nbf"]

    # Identity fields
    for field in ("sub", "iss", "aud", "jti"):
        if field in payload:
            analysis[field] = payload[field]

    return analysis


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class JWTDecodeTool(BaseTool):
    """Decode a JWT token without verification."""

    name = "jwt_decode"
    description = (
        "Decode a JWT token (no cryptographic verification). "
        "Parses the header and payload, and analyzes common fields "
        "like expiration, issuer, and subject."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "token": {
                "type": "string",
                "description": "The JWT token string to decode.",
            },
        },
        "required": ["token"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        token = arguments["token"].strip()

        try:
            header, payload, signature = _decode_jwt_parts(token)
            analysis = _analyze_jwt(header, payload)
        except ValueError as e:
            return ToolResult(success=False, output=str(e))
        except Exception as e:
            return ToolResult(success=False, output=f"JWT decode error: {e}")

        lines = [
            "=== JWT Header ===",
            json.dumps(header, indent=2),
            "",
            "=== JWT Payload ===",
            json.dumps(payload, indent=2, default=str),
            "",
            "=== Analysis ===",
        ]
        for k, v in analysis.items():
            lines.append(f"  {k}: {v}")

        return ToolResult(
            success=True,
            output="\n".join(lines),
            data={
                "header": header,
                "payload": payload,
                "analysis": analysis,
                "signature_present": bool(signature),
            },
        )


class JWTValidateTool(BaseTool):
    """Validate JWT structure (no cryptographic verification)."""

    name = "jwt_validate"
    description = (
        "Check the structural validity of a JWT token. "
        "Verifies that it has 3 parts, valid base64url encoding, "
        "valid JSON in header and payload, and analyzes common fields."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "token": {
                "type": "string",
                "description": "The JWT token string to validate.",
            },
        },
        "required": ["token"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        token = arguments["token"].strip()
        issues: list[str] = []
        checks: dict[str, bool] = {}

        # Check 1: Three parts
        parts = token.split(".")
        checks["has_three_parts"] = len(parts) == 3
        if not checks["has_three_parts"]:
            issues.append(f"Expected 3 dot-separated parts, got {len(parts)}")
            return ToolResult(
                success=True,
                output=f"Invalid JWT structure: {'; '.join(issues)}",
                data={"valid": False, "checks": checks, "issues": issues},
            )

        # Check 2: Valid base64url header
        try:
            header_json = _base64url_decode(parts[0])
            checks["valid_header_base64"] = True
        except Exception:
            checks["valid_header_base64"] = False
            issues.append("Header is not valid base64url")

        # Check 3: Valid JSON header
        if checks.get("valid_header_base64"):
            try:
                header = json.loads(header_json)
                checks["valid_header_json"] = True
                # Check for required header fields
                checks["has_alg"] = "alg" in header
                if not checks["has_alg"]:
                    issues.append("Header missing 'alg' field")
            except json.JSONDecodeError:
                checks["valid_header_json"] = False
                issues.append("Header is not valid JSON")

        # Check 4: Valid base64url payload
        try:
            payload_json = _base64url_decode(parts[1])
            checks["valid_payload_base64"] = True
        except Exception:
            checks["valid_payload_base64"] = False
            issues.append("Payload is not valid base64url")

        # Check 5: Valid JSON payload
        if checks.get("valid_payload_base64"):
            try:
                payload = json.loads(payload_json)
                checks["valid_payload_json"] = True
            except json.JSONDecodeError:
                checks["valid_payload_json"] = False
                issues.append("Payload is not valid JSON")

        # Check 6: Signature present
        checks["has_signature"] = len(parts[2]) > 0
        if not checks["has_signature"]:
            issues.append("Signature part is empty")

        is_valid = all(checks.values())

        if is_valid:
            output = f"Valid JWT structure. All {len(checks)} checks passed."
        else:
            output = f"JWT structure issues ({len(issues)}):\n" + "\n".join(f"  - {i}" for i in issues)

        return ToolResult(
            success=True,
            output=output,
            data={"valid": is_valid, "checks": checks, "issues": issues},
        )
