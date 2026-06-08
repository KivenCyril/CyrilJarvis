"""Gateway system tests.

Tests API gateway features including request routing, middleware,
response transformation, caching, and error handling.
"""

from __future__ import annotations

import datetime
import json
import time
from dataclasses import dataclass, field
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Gateway Models
# ---------------------------------------------------------------------------

@dataclass
class GatewayRoute:
    path: str
    method: str = "GET"
    handler: str = ""
    middleware: list[str] = field(default_factory=list)
    rate_limit: int | None = None
    cache_ttl: int | None = None  # seconds
    auth_required: bool = False
    description: str = ""

    def matches(self, path: str, method: str) -> bool:
        if self.method.upper() != method.upper():
            return False
        if self.path == path:
            return True
        # Simple path parameter matching
        route_parts = self.path.strip("/").split("/")
        path_parts = path.strip("/").split("/")
        if len(route_parts) != len(path_parts):
            return False
        for rp, pp in zip(route_parts, path_parts):
            if rp.startswith("{") and rp.endswith("}"):
                continue  # Parameter matches anything
            if rp != pp:
                return False
        return True

    def extract_params(self, path: str) -> dict[str, str]:
        params = {}
        route_parts = self.path.strip("/").split("/")
        path_parts = path.strip("/").split("/")
        for rp, pp in zip(route_parts, path_parts):
            if rp.startswith("{") and rp.endswith("}"):
                param_name = rp[1:-1]
                params[param_name] = pp
        return params


@dataclass
class GatewayRequest:
    path: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    body: dict | None = None
    query_params: dict[str, str] = field(default_factory=dict)
    client_ip: str = "127.0.0.1"
    timestamp: float = 0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


@dataclass
class GatewayResponse:
    status_code: int = 200
    body: dict | None = None
    headers: dict[str, str] = field(default_factory=dict)
    cached: bool = False
    latency_ms: float = 0


@dataclass
class CacheEntry:
    key: str
    value: Any
    created_at: float = 0
    ttl: int = 60  # seconds

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()

    @property
    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.ttl


class GatewayCache:
    """Simple in-memory cache for the gateway."""

    def __init__(self):
        self.entries: dict[str, CacheEntry] = {}
        self.hits: int = 0
        self.misses: int = 0

    def get(self, key: str) -> Any | None:
        entry = self.entries.get(key)
        if entry and not entry.is_expired:
            self.hits += 1
            return entry.value
        if entry and entry.is_expired:
            del self.entries[key]
        self.misses += 1
        return None

    def set(self, key: str, value: Any, ttl: int = 60) -> None:
        self.entries[key] = CacheEntry(key=key, value=value, ttl=ttl)

    def invalidate(self, key: str) -> bool:
        if key in self.entries:
            del self.entries[key]
            return True
        return False

    def clear(self) -> int:
        count = len(self.entries)
        self.entries.clear()
        return count

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total * 100, 1) if total > 0 else 0


class APIGateway:
    """Simple API gateway with routing, caching, and middleware."""

    def __init__(self):
        self.routes: list[GatewayRoute] = []
        self.cache = GatewayCache()
        self.request_count: int = 0
        self.error_count: int = 0

    def add_route(self, route: GatewayRoute) -> None:
        self.routes.append(route)

    def find_route(self, path: str, method: str) -> GatewayRoute | None:
        for route in self.routes:
            if route.matches(path, method):
                return route
        return None

    def handle(self, request: GatewayRequest) -> GatewayResponse:
        self.request_count += 1
        start = time.time()

        route = self.find_route(request.path, request.method)
        if not route:
            self.error_count += 1
            return GatewayResponse(status_code=404, body={"error": "Not Found"})

        # Check auth
        if route.auth_required and "Authorization" not in request.headers:
            self.error_count += 1
            return GatewayResponse(status_code=401, body={"error": "Unauthorized"})

        # Check cache
        if route.cache_ttl and request.method == "GET":
            cache_key = f"{request.method}:{request.path}"
            cached = self.cache.get(cache_key)
            if cached is not None:
                latency = round((time.time() - start) * 1000, 2)
                return GatewayResponse(
                    status_code=200, body=cached, cached=True, latency_ms=latency,
                )

        # Extract params
        params = route.extract_params(request.path)

        # Simulate response
        response_body = {
            "handler": route.handler,
            "params": params,
            "method": request.method,
        }

        # Cache if applicable
        if route.cache_ttl and request.method == "GET":
            cache_key = f"{request.method}:{request.path}"
            self.cache.set(cache_key, response_body, route.cache_ttl)

        latency = round((time.time() - start) * 1000, 2)
        return GatewayResponse(
            status_code=200, body=response_body, latency_ms=latency,
        )

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "total_requests": self.request_count,
            "error_count": self.error_count,
            "error_rate": round(self.error_count / self.request_count * 100, 1) if self.request_count else 0,
            "cache_hit_rate": self.cache.hit_rate,
            "routes": len(self.routes),
        }


# ---------------------------------------------------------------------------
# Tests: GatewayRoute
# ---------------------------------------------------------------------------

class TestGatewayRoute:
    def test_exact_match(self):
        route = GatewayRoute(path="/health", method="GET")
        assert route.matches("/health", "GET") is True
        assert route.matches("/health", "POST") is False
        assert route.matches("/other", "GET") is False

    def test_param_match(self):
        route = GatewayRoute(path="/users/{id}", method="GET")
        assert route.matches("/users/123", "GET") is True
        assert route.matches("/users/abc", "GET") is True
        assert route.matches("/users", "GET") is False

    def test_extract_params(self):
        route = GatewayRoute(path="/specs/{spec_id}/steps/{step_id}")
        params = route.extract_params("/specs/s1/steps/st2")
        assert params["spec_id"] == "s1"
        assert params["step_id"] == "st2"

    def test_no_params(self):
        route = GatewayRoute(path="/health")
        params = route.extract_params("/health")
        assert params == {}


# ---------------------------------------------------------------------------
# Tests: GatewayCache
# ---------------------------------------------------------------------------

class TestGatewayCache:
    def test_set_and_get(self):
        cache = GatewayCache()
        cache.set("key1", {"data": "value"})
        assert cache.get("key1") == {"data": "value"}

    def test_miss(self):
        cache = GatewayCache()
        assert cache.get("missing") is None

    def test_expired(self):
        cache = GatewayCache()
        cache.entries["old"] = CacheEntry(
            key="old", value="expired",
            created_at=time.time() - 1000, ttl=1,
        )
        assert cache.get("old") is None

    def test_invalidate(self):
        cache = GatewayCache()
        cache.set("key", "value")
        assert cache.invalidate("key") is True
        assert cache.get("key") is None

    def test_clear(self):
        cache = GatewayCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cleared = cache.clear()
        assert cleared == 2

    def test_hit_rate(self):
        cache = GatewayCache()
        cache.set("key", "val")
        cache.get("key")  # hit
        cache.get("key")  # hit
        cache.get("miss")  # miss
        assert cache.hit_rate > 60


# ---------------------------------------------------------------------------
# Tests: APIGateway
# ---------------------------------------------------------------------------

class TestAPIGateway:
    def test_handle_existing_route(self):
        gw = APIGateway()
        gw.add_route(GatewayRoute(path="/health", method="GET", handler="health_check"))
        resp = gw.handle(GatewayRequest(path="/health"))
        assert resp.status_code == 200

    def test_handle_not_found(self):
        gw = APIGateway()
        resp = gw.handle(GatewayRequest(path="/missing"))
        assert resp.status_code == 404

    def test_handle_auth_required(self):
        gw = APIGateway()
        gw.add_route(GatewayRoute(path="/admin", method="GET", auth_required=True))
        resp = gw.handle(GatewayRequest(path="/admin"))
        assert resp.status_code == 401

    def test_handle_auth_with_token(self):
        gw = APIGateway()
        gw.add_route(GatewayRoute(path="/admin", method="GET", auth_required=True))
        resp = gw.handle(GatewayRequest(
            path="/admin",
            headers={"Authorization": "Bearer token"},
        ))
        assert resp.status_code == 200

    def test_caching(self):
        gw = APIGateway()
        gw.add_route(GatewayRoute(path="/data", method="GET", cache_ttl=60))
        r1 = gw.handle(GatewayRequest(path="/data"))
        assert r1.cached is False
        r2 = gw.handle(GatewayRequest(path="/data"))
        assert r2.cached is True

    def test_stats(self):
        gw = APIGateway()
        gw.add_route(GatewayRoute(path="/health", method="GET"))
        gw.handle(GatewayRequest(path="/health"))
        gw.handle(GatewayRequest(path="/missing"))
        stats = gw.stats
        assert stats["total_requests"] == 2
        assert stats["error_count"] == 1

    def test_param_routing(self):
        gw = APIGateway()
        gw.add_route(GatewayRoute(path="/users/{id}", method="GET", handler="get_user"))
        resp = gw.handle(GatewayRequest(path="/users/42"))
        assert resp.status_code == 200
        assert resp.body["params"]["id"] == "42"

    def test_multiple_routes(self):
        gw = APIGateway()
        gw.add_route(GatewayRoute(path="/a", method="GET", handler="handler_a"))
        gw.add_route(GatewayRoute(path="/b", method="GET", handler="handler_b"))
        gw.add_route(GatewayRoute(path="/c", method="POST", handler="handler_c"))
        assert gw.handle(GatewayRequest(path="/a")).body["handler"] == "handler_a"
        assert gw.handle(GatewayRequest(path="/b")).body["handler"] == "handler_b"
        assert gw.handle(GatewayRequest(path="/c", method="POST")).body["handler"] == "handler_c"
