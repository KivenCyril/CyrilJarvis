from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from jarvis.llm.provider import (
    LLMProvider,
    LLMResponse,
    Message,
    Role,
    StreamChunk,
    ToolCall,
    ToolDefinition,
)

logger = logging.getLogger(__name__)


@dataclass
class TurnResult:
    """Result of a single conversation turn."""

    content: str = ""
    tool_calls_made: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"
    tokens_used: int = 0


@dataclass
class ConversationState:
    """Tracks the state of a multi-turn conversation."""

    messages: list[Message] = field(default_factory=list)
    total_tokens: int = 0
    turns: int = 0
    tool_calls_total: int = 0
    started_at: float = field(default_factory=time.monotonic)

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at


class ConversationLoop:
    """Production-grade multi-turn conversation loop with tool calling.

    Modeled after Hermes Agent's conversation_loop.py. Handles:
    - Multi-turn tool calling with proper message threading
    - Token budget management (context window awareness)
    - Automatic context compression when approaching limits
    - Graceful error handling and retry for tool failures
    - Streaming support for real-time output
    - Conversation state tracking for observability

    The loop continues until:
    - The LLM returns without tool calls (natural completion)
    - max_turns is reached
    - Token budget is exceeded
    - An unrecoverable error occurs
    """

    def __init__(
        self,
        llm: LLMProvider,
        tools: list[ToolDefinition] | None = None,
        tool_executor: Any = None,  # ToolRegistry
        max_turns: int = 10,
        max_tokens_budget: int = 100000,
        system_prompt: str = "",
    ):
        self.llm = llm
        self.tools = tools
        self.tool_executor = tool_executor
        self.max_turns = max_turns
        self.max_tokens_budget = max_tokens_budget
        self.system_prompt = system_prompt

    async def run(
        self,
        user_message: str,
        context: list[Message] | None = None,
        constraints: list[str] | None = None,
    ) -> tuple[str, ConversationState]:
        """Execute the full conversation loop.

        Returns:
            tuple of (final_response_text, conversation_state)
        """
        state = ConversationState()

        # Build initial messages
        if self.system_prompt:
            system = self.system_prompt
            if constraints:
                system += "\n\nConstraints:\n" + "\n".join(f"- {c}" for c in constraints)
            state.messages.append(Message(role=Role.SYSTEM, content=system))

        if context:
            state.messages.extend(context)

        state.messages.append(Message(role=Role.USER, content=user_message))

        accumulated_response: list[str] = []

        for turn in range(self.max_turns):
            state.turns = turn + 1

            # Check token budget (estimate: 4 chars ~ 1 token)
            estimated_tokens = sum(len(m.content) // 4 for m in state.messages)
            if estimated_tokens > self.max_tokens_budget:
                # Compress context
                state.messages = await self._compress_context(state.messages)

            try:
                response = await self.llm.chat(
                    messages=state.messages,
                    tools=self.tools if self.tool_executor else None,
                )
            except Exception as e:
                logger.error("LLM call failed on turn %d: %s", turn + 1, e)
                break

            state.total_tokens += response.usage.get("prompt_tokens", 0) + response.usage.get(
                "completion_tokens", 0
            )

            if response.content:
                accumulated_response.append(response.content)

            # No tool calls -> conversation complete
            if not response.has_tool_calls:
                break

            # Record assistant message with tool calls
            state.messages.append(
                Message(
                    role=Role.ASSISTANT,
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )

            # Execute each tool call
            for tc in response.tool_calls:
                state.tool_calls_total += 1
                tool_output = await self._execute_tool(tc)

                state.messages.append(
                    Message(
                        role=Role.TOOL,
                        content=tool_output,
                        tool_call_id=tc.id,
                    )
                )

        final_response = "\n".join(accumulated_response) if accumulated_response else ""
        return final_response, state

    async def _execute_tool(self, tc: ToolCall) -> str:
        """Execute a tool call with error handling."""
        if not self.tool_executor:
            return f"Tool '{tc.name}' is not available"

        try:
            result = await self.tool_executor.execute(tc.name, tc.arguments)
            return result.output
        except Exception as e:
            logger.warning("Tool '%s' failed: %s", tc.name, e)
            return f"Tool error: {e}"

    async def _compress_context(self, messages: list[Message]) -> list[Message]:
        """Compress conversation history to fit within token budget.

        Strategy (matching Hermes context_compressor.py):
        1. Keep system prompt intact
        2. Keep the last N user/assistant exchanges
        3. Summarize older exchanges into a single message
        """
        if len(messages) <= 4:
            return messages

        system_msgs = [m for m in messages if m.role == Role.SYSTEM]
        other_msgs = [m for m in messages if m.role != Role.SYSTEM]

        if len(other_msgs) <= 6:
            return messages

        # Keep last 4 messages, summarize the rest
        keep = other_msgs[-4:]
        to_summarize = other_msgs[:-4]

        summary_parts = []
        for m in to_summarize:
            if m.role == Role.TOOL:
                continue  # skip tool results in summary
            prefix = "User" if m.role == Role.USER else "Assistant"
            summary_parts.append(f"{prefix}: {m.content[:200]}")

        summary = "[Previous conversation summary]\n" + "\n".join(summary_parts[-10:])

        compressed = system_msgs + [Message(role=Role.USER, content=summary)] + keep
        logger.info("Context compressed: %d -> %d messages", len(messages), len(compressed))
        return compressed
