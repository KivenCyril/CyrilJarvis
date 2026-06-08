"""Custom Agent Creation Demo.

Shows how to create a custom specialist agent with:
- Custom agent card with skills and domain
- Custom routing logic for intent matching
- Custom execution with tool integration
- Quality feedback loop

Usage:
    python examples/advanced/custom_agent.py
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Agent primitives (simplified versions of JARVIS core)
# ---------------------------------------------------------------------------

@dataclass
class AgentCard:
    """Describes an agent's capabilities."""
    name: str
    description: str
    domain: str
    skills: list[str] = field(default_factory=list)
    can_delegate: bool = False
    version: str = "1.0.0"
    model: str = "gpt-4"
    max_tokens: int = 4096
    temperature: float = 0.7
    system_prompt: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class AgentResult:
    """Result from an agent execution."""
    success: bool
    output: str
    agent_name: str
    metadata: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    tools_used: list[str] = field(default_factory=list)
    tokens_used: int = 0


class BaseAgent:
    """Base class for custom agents."""

    def __init__(self, card: AgentCard):
        self.card = card
        self.name = card.name
        self.execution_count = 0
        self.success_count = 0

    def score(self, message: str) -> float:
        """Score how well this agent can handle a message (0-1)."""
        msg_lower = message.lower()
        score = 0.0
        for skill in self.card.skills:
            if skill.lower() in msg_lower:
                score += 0.3
        for tag in self.card.tags:
            if tag.lower() in msg_lower:
                score += 0.1
        if self.card.domain.lower() in msg_lower:
            score += 0.2
        return min(score, 1.0)

    async def handle(self, message: str) -> AgentResult:
        """Process a message and return a result."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Custom Agent: SQL Analyst
# ---------------------------------------------------------------------------

class SQLAnalystAgent(BaseAgent):
    """A specialist agent for SQL queries and database analysis."""

    def __init__(self):
        super().__init__(AgentCard(
            name="sql-analyst",
            description=(
                "Specialist in SQL queries, database schema analysis, "
                "query optimization, and data modeling."
            ),
            domain="databases",
            skills=["sql", "query optimization", "schema design", "data modeling",
                    "database", "query", "table", "index"],
            tags=["sql", "database", "analytics", "data", "query", "schema"],
            system_prompt=(
                "You are an expert SQL analyst. You help users write efficient "
                "queries, design schemas, and optimize database performance."
            ),
            temperature=0.3,  # Lower temperature for precise SQL
        ))
        self.query_history: list[dict] = []

    def score(self, message: str) -> float:
        """Enhanced scoring with SQL-specific pattern matching."""
        base_score = super().score(message)
        msg_lower = message.lower()

        # SQL keywords boost
        sql_keywords = [
            "select", "insert", "update", "delete", "join", "where",
            "group by", "order by", "having", "index", "table",
            "constraint", "foreign key", "primary key", "aggregate",
        ]
        keyword_matches = sum(1 for kw in sql_keywords if kw in msg_lower)
        keyword_score = min(keyword_matches * 0.15, 0.5)

        # Pattern matching for SQL queries
        if re.search(r'\b(select|insert|update|delete)\b', msg_lower, re.IGNORECASE):
            keyword_score += 0.3

        return min(base_score + keyword_score, 1.0)

    async def handle(self, message: str) -> AgentResult:
        """Handle a database-related query."""
        self.execution_count += 1

        # Simulate SQL analysis
        msg_lower = message.lower()

        if "optimize" in msg_lower or "performance" in msg_lower:
            output = self._handle_optimization(message)
        elif "schema" in msg_lower or "design" in msg_lower:
            output = self._handle_schema_design(message)
        elif any(kw in msg_lower for kw in ["select", "query", "find", "get"]):
            output = self._handle_query(message)
        else:
            output = self._handle_general(message)

        self.success_count += 1

        result = AgentResult(
            success=True,
            output=output,
            agent_name=self.name,
            confidence=0.9,
            tools_used=["sqlite_query", "sqlite_schemas"],
            metadata={"query_count": len(self.query_history)},
        )

        self.query_history.append({
            "message": message,
            "output": output[:100],
        })

        return result

    def _handle_optimization(self, message: str) -> str:
        return (
            "Query Optimization Suggestions:\n"
            "1. Add index on frequently filtered columns\n"
            "2. Use EXPLAIN ANALYZE to identify bottlenecks\n"
            "3. Consider denormalization for read-heavy tables\n"
            "4. Replace SELECT * with specific columns\n"
            "5. Use covering indexes for common queries"
        )

    def _handle_schema_design(self, message: str) -> str:
        return (
            "Schema Design Recommendations:\n"
            "- Use normalized forms (3NF) for transactional data\n"
            "- Add created_at/updated_at timestamps to all tables\n"
            "- Use UUIDs for distributed systems, SERIAL for single-node\n"
            "- Define foreign key constraints for referential integrity\n"
            "- Add CHECK constraints for data validation"
        )

    def _handle_query(self, message: str) -> str:
        return (
            "Sample Query:\n"
            "```sql\n"
            "SELECT u.name, COUNT(o.id) as order_count, SUM(o.total) as revenue\n"
            "FROM users u\n"
            "LEFT JOIN orders o ON u.id = o.user_id\n"
            "WHERE o.created_at >= CURRENT_DATE - INTERVAL '30 days'\n"
            "GROUP BY u.name\n"
            "HAVING COUNT(o.id) > 5\n"
            "ORDER BY revenue DESC\n"
            "LIMIT 10;\n"
            "```"
        )

    def _handle_general(self, message: str) -> str:
        return f"I can help with database questions. Your query: {message}"


# ---------------------------------------------------------------------------
# Custom Agent: API Designer
# ---------------------------------------------------------------------------

class APIDesignerAgent(BaseAgent):
    """A specialist agent for REST API design and review."""

    def __init__(self):
        super().__init__(AgentCard(
            name="api-designer",
            description="Expert in REST API design, OpenAPI specs, and API best practices.",
            domain="api-design",
            skills=["rest", "api design", "openapi", "endpoint", "http"],
            tags=["api", "rest", "endpoint", "http", "openapi", "swagger"],
            temperature=0.5,
        ))

    async def handle(self, message: str) -> AgentResult:
        self.execution_count += 1

        # Generate API design advice
        output = (
            "API Design Recommendations:\n"
            "1. Use resource-based URLs: /users, /users/{id}\n"
            "2. HTTP methods: GET (read), POST (create), PUT (update), DELETE\n"
            "3. Return proper status codes: 200, 201, 400, 404, 500\n"
            "4. Use pagination: ?page=1&per_page=25\n"
            "5. Version your API: /v1/users\n"
            "6. Use consistent error response format\n"
            "7. Support filtering: ?status=active&role=admin"
        )

        self.success_count += 1
        return AgentResult(
            success=True, output=output, agent_name=self.name,
            confidence=0.85,
        )


# ---------------------------------------------------------------------------
# Simple routing demo
# ---------------------------------------------------------------------------

async def main():
    """Demonstrate custom agent creation and routing."""
    # Create agents
    agents = [
        SQLAnalystAgent(),
        APIDesignerAgent(),
    ]

    print("Registered custom agents:")
    for agent in agents:
        print(f"  - {agent.name}: {agent.card.description[:60]}...")
        print(f"    Domain: {agent.card.domain}")
        print(f"    Skills: {', '.join(agent.card.skills[:5])}...")

    # Test routing with different messages
    test_messages = [
        "How do I optimize this slow SQL query?",
        "Design a REST API for a user management service",
        "Write a SELECT query to find top customers",
        "What are best practices for API versioning?",
        "Help me design a database schema for an e-commerce app",
    ]

    print(f"\n{'='*60}")
    print("Routing test messages to best-matching agent:")
    print(f"{'='*60}\n")

    for message in test_messages:
        scores = [(agent, agent.score(message)) for agent in agents]
        scores.sort(key=lambda x: x[1], reverse=True)

        best_agent, best_score = scores[0]

        print(f"Message: \"{message}\"")
        for agent, score in scores:
            bar = "X" * int(score * 20) + "." * (20 - int(score * 20))
            print(f"  {agent.name}: {score:.2f} [{bar}]")

        if best_score > 0:
            result = await best_agent.handle(message)
            print(f"  -> Routed to: {result.agent_name}")
            print(f"  -> Output preview: {result.output[:80]}...")
        else:
            print("  -> No suitable agent found")
        print()

    # Show stats
    print("\nAgent statistics:")
    for agent in agents:
        rate = (agent.success_count / agent.execution_count * 100) if agent.execution_count else 0
        print(f"  {agent.name}: {agent.execution_count} executions, {rate:.0f}% success rate")


if __name__ == "__main__":
    asyncio.run(main())
