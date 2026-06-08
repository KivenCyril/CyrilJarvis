"""Webhook Integration Demo.

Shows how to set up webhook notifications from JARVIS events,
including payload formatting, retry logic, and multi-platform
delivery (Slack, Discord, generic HTTP).

Usage:
    python examples/advanced/webhook_integration.py
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Webhook configuration
# ---------------------------------------------------------------------------

@dataclass
class WebhookConfig:
    """Configuration for a webhook endpoint."""
    name: str
    url: str
    platform: str  # slack, discord, generic
    events: list[str] = field(default_factory=list)  # event topics to subscribe to
    secret: str = ""
    enabled: bool = True
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    timeout_seconds: float = 10.0
    headers: dict[str, str] = field(default_factory=dict)
    transform: str = "default"  # default, slack, discord

    def matches_event(self, event_topic: str) -> bool:
        """Check if this webhook should receive an event."""
        if not self.events:
            return True  # Subscribe to all events
        for pattern in self.events:
            if pattern == event_topic:
                return True
            if pattern.endswith("*") and event_topic.startswith(pattern[:-1]):
                return True
        return False


@dataclass
class WebhookDelivery:
    """Record of a webhook delivery attempt."""
    webhook_name: str
    event_topic: str
    status: str = "pending"  # pending, delivered, failed, retrying
    attempts: int = 0
    last_error: str | None = None
    response_code: int | None = None
    delivered_at: str | None = None
    payload_size: int = 0

    @property
    def is_final(self) -> bool:
        return self.status in ("delivered", "failed")


# ---------------------------------------------------------------------------
# Payload transformers
# ---------------------------------------------------------------------------

def transform_slack(event: dict) -> dict:
    """Transform a JARVIS event into a Slack-compatible payload."""
    topic = event.get("topic", "unknown")
    data = event.get("data", {})

    # Color based on event type
    color_map = {
        "spec.completed": "#22c55e",
        "spec.failed": "#ef4444",
        "deploy.started": "#3b82f6",
        "deploy.completed": "#22c55e",
        "error.occurred": "#ef4444",
    }
    color = color_map.get(topic, "#94a3b8")

    return {
        "attachments": [{
            "color": color,
            "title": f"JARVIS Event: {topic}",
            "text": json.dumps(data, indent=2),
            "footer": f"Source: {event.get('source', 'jarvis')}",
            "ts": event.get("timestamp", ""),
            "fields": [
                {"title": "Topic", "value": topic, "short": True},
                {"title": "Priority", "value": event.get("priority", "normal"), "short": True},
            ],
        }],
    }


def transform_discord(event: dict) -> dict:
    """Transform a JARVIS event into a Discord webhook payload."""
    topic = event.get("topic", "unknown")
    data = event.get("data", {})

    color_map = {
        "spec.completed": 2264592,   # green
        "spec.failed": 15548997,     # red
        "deploy.started": 3901635,   # blue
        "error.occurred": 15548997,  # red
    }
    color = color_map.get(topic, 9807270)

    return {
        "embeds": [{
            "title": f"JARVIS: {topic}",
            "description": json.dumps(data, indent=2)[:2000],
            "color": color,
            "footer": {"text": f"Source: {event.get('source', 'jarvis')}"},
            "fields": [
                {"name": "Topic", "value": topic, "inline": True},
                {"name": "Priority", "value": event.get("priority", "normal"), "inline": True},
            ],
        }],
    }


def transform_default(event: dict) -> dict:
    """Pass through the event as-is (generic webhook)."""
    return {
        "event_type": event.get("topic", "unknown"),
        "timestamp": event.get("timestamp", ""),
        "source": event.get("source", "jarvis"),
        "priority": event.get("priority", "normal"),
        "data": event.get("data", {}),
    }


TRANSFORMERS: dict[str, Callable] = {
    "slack": transform_slack,
    "discord": transform_discord,
    "default": transform_default,
}


# ---------------------------------------------------------------------------
# Webhook manager
# ---------------------------------------------------------------------------

class WebhookManager:
    """Manage webhook subscriptions and delivery."""

    def __init__(self):
        self.webhooks: list[WebhookConfig] = []
        self.deliveries: list[WebhookDelivery] = []
        self.dead_letter_queue: list[dict] = []

    def register(self, webhook: WebhookConfig) -> None:
        """Register a webhook endpoint."""
        self.webhooks.append(webhook)
        print(f"  Registered webhook: {webhook.name} -> {webhook.url}")
        print(f"    Platform: {webhook.platform}, Events: {webhook.events or ['*']}")

    def unregister(self, name: str) -> bool:
        """Remove a webhook by name."""
        before = len(self.webhooks)
        self.webhooks = [w for w in self.webhooks if w.name != name]
        return len(self.webhooks) < before

    async def dispatch(self, event: dict) -> list[WebhookDelivery]:
        """Dispatch an event to all matching webhooks."""
        topic = event.get("topic", "unknown")
        matching = [w for w in self.webhooks if w.enabled and w.matches_event(topic)]

        if not matching:
            return []

        deliveries = []
        for webhook in matching:
            delivery = await self._deliver(webhook, event)
            deliveries.append(delivery)
            self.deliveries.append(delivery)

        return deliveries

    async def _deliver(self, webhook: WebhookConfig, event: dict) -> WebhookDelivery:
        """Deliver an event to a webhook with retry logic."""
        delivery = WebhookDelivery(
            webhook_name=webhook.name,
            event_topic=event.get("topic", "unknown"),
        )

        # Transform payload
        transformer = TRANSFORMERS.get(webhook.transform, transform_default)
        payload = transformer(event)
        delivery.payload_size = len(json.dumps(payload))

        # Simulate delivery with retries
        for attempt in range(1, webhook.max_retries + 1):
            delivery.attempts = attempt
            delivery.status = "retrying" if attempt > 1 else "pending"

            try:
                # Simulate HTTP POST (in real code, use httpx/aiohttp)
                success = await self._simulate_http_post(webhook.url, payload)

                if success:
                    delivery.status = "delivered"
                    delivery.response_code = 200
                    delivery.delivered_at = str(time.time())
                    return delivery
                else:
                    delivery.last_error = "Server returned non-200 status"
                    delivery.response_code = 500

            except Exception as exc:
                delivery.last_error = str(exc)

            if attempt < webhook.max_retries:
                await asyncio.sleep(webhook.retry_delay_seconds * attempt)

        # All retries exhausted
        delivery.status = "failed"
        self.dead_letter_queue.append({
            "webhook": webhook.name,
            "event": event,
            "error": delivery.last_error,
            "attempts": delivery.attempts,
        })
        return delivery

    async def _simulate_http_post(self, url: str, payload: dict) -> bool:
        """Simulate an HTTP POST request."""
        await asyncio.sleep(0.1)  # Simulate network latency
        # 90% success rate for simulation
        import random
        return random.random() < 0.9

    def get_stats(self) -> dict[str, Any]:
        """Get delivery statistics."""
        total = len(self.deliveries)
        delivered = sum(1 for d in self.deliveries if d.status == "delivered")
        failed = sum(1 for d in self.deliveries if d.status == "failed")
        return {
            "total_deliveries": total,
            "delivered": delivered,
            "failed": failed,
            "success_rate": round(delivered / total * 100, 1) if total else 0,
            "dead_letter_count": len(self.dead_letter_queue),
            "registered_webhooks": len(self.webhooks),
        }


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

async def main():
    """Demonstrate webhook integration."""
    manager = WebhookManager()

    # Register webhooks
    print("Registering webhooks:")
    manager.register(WebhookConfig(
        name="slack-deploys",
        url="https://hooks.slack.com/services/T00/B00/xxxx",
        platform="slack",
        events=["deploy.*", "error.occurred"],
        transform="slack",
    ))

    manager.register(WebhookConfig(
        name="discord-all",
        url="https://discord.com/api/webhooks/123/token",
        platform="discord",
        events=[],  # All events
        transform="discord",
    ))

    manager.register(WebhookConfig(
        name="monitoring-api",
        url="https://monitoring.example.com/webhook",
        platform="generic",
        events=["error.*", "spec.failed"],
        transform="default",
    ))

    # Simulate events
    events = [
        {"topic": "spec.created", "source": "api", "priority": "normal", "data": {"spec_id": "s1"}, "timestamp": "2025-06-01T10:00:00Z"},
        {"topic": "deploy.started", "source": "ci", "priority": "high", "data": {"version": "1.3.0"}, "timestamp": "2025-06-01T10:01:00Z"},
        {"topic": "deploy.completed", "source": "ci", "priority": "high", "data": {"version": "1.3.0", "status": "success"}, "timestamp": "2025-06-01T10:05:00Z"},
        {"topic": "error.occurred", "source": "system", "priority": "high", "data": {"message": "Connection timeout"}, "timestamp": "2025-06-01T10:10:00Z"},
        {"topic": "spec.completed", "source": "agent", "priority": "normal", "data": {"spec_id": "s1"}, "timestamp": "2025-06-01T10:15:00Z"},
    ]

    print(f"\nDispatching {len(events)} events:")
    for event in events:
        deliveries = await manager.dispatch(event)
        topic = event["topic"]
        print(f"\n  Event: {topic}")
        for d in deliveries:
            status_icon = "v" if d.status == "delivered" else "x"
            print(f"    [{status_icon}] -> {d.webhook_name}: {d.status} (attempts: {d.attempts})")

    # Print stats
    print(f"\n{'='*40}")
    print("Delivery Statistics:")
    stats = manager.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    if manager.dead_letter_queue:
        print(f"\nDead Letter Queue ({len(manager.dead_letter_queue)} items):")
        for item in manager.dead_letter_queue:
            print(f"  - {item['webhook']}: {item['event']['topic']} ({item['error']})")


if __name__ == "__main__":
    asyncio.run(main())
