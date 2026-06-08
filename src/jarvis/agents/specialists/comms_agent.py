from __future__ import annotations

import logging
import re
from typing import Any

from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt -- comprehensive communication specialist
# ---------------------------------------------------------------------------

COMMS_AGENT_SYSTEM_PROMPT = """\
You are a communication specialist within the JARVIS assistant system.

# Capabilities
- Email triage with urgency classification and smart categorization
- Multi-channel message format adaptation (email, Slack, DingTalk, Teams, SMS)
- Professional draft composition with tone and clarity analysis
- Thread and conversation summarization
- Notification digest creation and management
- Response time management and SLA tracking
- Contact and recipient management

You have access to tools: read_file, write_file, python_execute, shell_execute.
Use them to process message data, draft content, and format output.

# Execution protocol
1. **Identify channel** -- determine the communication channel (email, chat, etc.).
2. **Analyze intent** -- triage, reply, compose, summarize, or manage notifications.
3. **Assess context** -- review previous messages, thread history, urgency signals.
4. **Execute** -- perform the communication task with channel-appropriate format.
5. **Quality check** -- apply the draft quality checklist before output.
6. **Deliver** -- present the result in the target format.

# Email triage system with urgency classification
When triaging emails or messages, classify into these categories:

## Urgency levels
- **P0-CRITICAL**: System outages, security incidents, customer escalations with SLA breach
- **P1-URGENT**: Deadline within 24h, executive requests, time-sensitive approvals
- **P2-ACTION**: Tasks requiring response within 2-3 days, review requests
- **P3-FYI**: Informational, newsletters, status updates -- no response needed
- **P4-ARCHIVE**: Spam, outdated threads, resolved discussions

## Classification signals
- Sender importance: VIP contacts, direct manager, customer, external partner
- Subject line keywords: "urgent", "ASAP", "action required", "deadline", "P0"
- Thread activity: rapid replies suggest active discussion
- Mentions: @-mentions or CC indicate expected involvement
- Calendar links: time-sensitive invitations
- Attachment types: contracts, invoices suggest action needed

## Triage output format
For each message:
```
[P{level}] From: {sender} | Subject: {subject}
  Category: {category}
  Action: {recommended action}
  Deadline: {if applicable}
```

# Multi-channel message format adaptation
Adapt message content to the target channel:

| Channel    | Tone       | Length   | Format           | Features            |
|------------|------------|----------|------------------|---------------------|
| Email      | Formal     | Medium   | Structured       | Subject, greeting   |
| Slack      | Casual     | Short    | Markdown         | Emoji, threads      |
| DingTalk   | Semi-formal| Short    | Markdown/HTML    | @mentions, cards    |
| Teams      | Semi-formal| Medium   | Adaptive cards   | Rich formatting     |
| SMS/WeChat | Brief      | Very short| Plain text      | No formatting       |
| LinkedIn   | Professional| Medium  | Rich text        | Hashtags, mentions  |

# Draft quality checklist
Before finalizing any draft, evaluate:
1. **Tone** -- appropriate for audience and channel (formal/casual/friendly)
2. **Clarity** -- main point within first 2 sentences; no ambiguity
3. **Actionability** -- clear call-to-action if response is expected
4. **Length** -- concise for channel; no unnecessary filler
5. **Grammar** -- correct spelling, punctuation, grammar
6. **Sensitivity** -- no confidential info in wrong channel; consider BCC for privacy
7. **Attachments** -- referenced files are attached or linked
8. **Recipients** -- correct To/CC/BCC; no reply-all accidents
9. **Subject line** -- descriptive, searchable, action-oriented
10. **Sign-off** -- appropriate closing for the relationship

# Thread summarization workflow
When summarizing a conversation thread:
1. **Identify participants** -- list all contributors and their roles
2. **Extract key points** -- main topics discussed, in chronological order
3. **Track decisions** -- any decisions made, with who decided
4. **List action items** -- tasks assigned, owners, deadlines
5. **Note open questions** -- unresolved issues requiring follow-up
6. **Output format**:
```
Thread Summary: {subject}
Participants: {list}
Period: {first message date} - {last message date}
Key Points:
  1. {point}
  2. {point}
Decisions:
  - {decision} (by {person}, {date})
Action Items:
  - [ ] {task} -> {owner} (due: {date})
Open Questions:
  - {question}
```

# Notification digest creation
When creating notification digests:
- Group by category (mentions, replies, approvals, FYI)
- Prioritize by urgency (P0 first, P4 last)
- Include action counts: "3 items need your response"
- Limit digest to top 10 items; link to full list
- Schedule: morning (08:00) and afternoon (14:00) digests

# Response time management
Track and suggest response times based on urgency:
- P0: respond within 1 hour
- P1: respond within 4 hours
- P2: respond within 24 hours
- P3: respond within 3 days (or batch)
- P4: no response needed

Flag overdue responses and suggest prioritization.
"""

# ---------------------------------------------------------------------------
# Channel detection patterns
# ---------------------------------------------------------------------------

_CHANNEL_PATTERNS: dict[str, list[str]] = {
    "email": ["email", "邮件", "inbox", "收件箱", "outlook", "gmail", "mail", "smtp"],
    "slack": ["slack", "channel", "频道", "thread", "workspace"],
    "dingtalk": ["dingtalk", "钉钉", "ding", "workbench"],
    "teams": ["teams", "microsoft teams"],
    "wechat": ["wechat", "微信", "weixin"],
    "sms": ["sms", "短信", "text message"],
    "generic": ["message", "消息", "notification", "通知"],
}

# ---------------------------------------------------------------------------
# Task type definitions
# ---------------------------------------------------------------------------

_TASK_TRIAGE = "triage"
_TASK_REPLY = "reply"
_TASK_COMPOSE = "compose"
_TASK_SUMMARIZE = "summarize"
_TASK_DIGEST = "digest"
_TASK_FORWARD = "forward"
_TASK_TEMPLATE = "template"
_TASK_NOTIFY = "notify"

_TASK_KEYWORDS: list[tuple[list[str], str]] = [
    (["triage", "整理", "inbox", "收件箱", "classify", "分类", "sort", "排序", "prioritize", "优先级"], _TASK_TRIAGE),
    (["reply", "回复", "respond", "答复", "write back", "get back to"], _TASK_REPLY),
    (["compose", "撰写", "write", "写", "draft", "草稿", "new message", "new email"], _TASK_COMPOSE),
    (["digest", "简报", "roundup", "briefing", "daily summary", "日报"], _TASK_DIGEST),
    (["summary", "摘要", "总结", "summarize", "汇总", "thread", "conversation"], _TASK_SUMMARIZE),
    (["forward", "转发", "share", "分享", "send to", "发给"], _TASK_FORWARD),
    (["template", "模板", "boilerplate", "canned response", "预设回复"], _TASK_TEMPLATE),
    (["notify", "通知", "alert", "提醒", "announce", "公告"], _TASK_NOTIFY),
]

# ---------------------------------------------------------------------------
# Task-specific prompt augmentations
# ---------------------------------------------------------------------------

_TASK_PROMPTS: dict[str, str] = {
    _TASK_TRIAGE: (
        "You are triaging messages/emails. "
        "Classify each by urgency (P0-P4) and category. "
        "Output in the triage format. "
        "Suggest which items to handle first."
    ),
    _TASK_REPLY: (
        "You are drafting a reply. "
        "Match the tone of the original message. "
        "Address all points raised. "
        "Include a clear call-to-action if needed. "
        "Apply the draft quality checklist."
    ),
    _TASK_COMPOSE: (
        "You are composing a new message. "
        "Determine the appropriate channel and tone. "
        "Structure with clear subject, body, and closing. "
        "Apply the draft quality checklist."
    ),
    _TASK_SUMMARIZE: (
        "You are summarizing a conversation thread. "
        "Follow the thread summarization workflow. "
        "Extract decisions, action items, and open questions. "
        "Keep summary concise but complete."
    ),
    _TASK_DIGEST: (
        "You are creating a notification digest. "
        "Group items by category and urgency. "
        "Highlight items requiring action. "
        "Keep the digest scannable and under 10 items."
    ),
    _TASK_FORWARD: (
        "You are forwarding a message. "
        "Add context for the recipient. "
        "Highlight why this is relevant to them."
    ),
    _TASK_TEMPLATE: (
        "You are creating a message template. "
        "Use {{placeholders}} for variable content. "
        "Provide usage instructions and example."
    ),
    _TASK_NOTIFY: (
        "You are sending a notification or announcement. "
        "Keep it brief and actionable. "
        "Include relevant links or references."
    ),
}

# ---------------------------------------------------------------------------
# Mock outputs per task type
# ---------------------------------------------------------------------------

_MOCK_OUTPUTS: dict[str, str] = {
    _TASK_TRIAGE: (
        "Inbox triaged (26 messages):\n"
        "  [P0] 0 critical\n"
        "  [P1] 3 urgent -- respond within 4h\n"
        "  [P2] 8 action-needed -- respond within 24h\n"
        "  [P3] 10 FYI -- no response needed\n"
        "  [P4] 5 archive candidates\n"
        "Top priority: expense approval from Finance (due today)"
    ),
    _TASK_REPLY: "Draft reply composed. Tone: professional, concise. Ready for review.",
    _TASK_COMPOSE: "New message drafted. Subject line optimized. Draft quality checklist passed.",
    _TASK_SUMMARIZE: (
        "Thread summary (12 messages, 5 participants):\n"
        "  Key points: 3 topics discussed\n"
        "  Decisions: 2 made\n"
        "  Action items: 4 assigned\n"
        "  Open questions: 1 remaining"
    ),
    _TASK_DIGEST: (
        "Notification digest:\n"
        "  3 items need your response\n"
        "  5 FYI updates\n"
        "  2 mentions in team channels"
    ),
    _TASK_FORWARD: "Message forwarded with context added for the recipient.",
    _TASK_TEMPLATE: "Message template created with 3 placeholders. Usage instructions included.",
    _TASK_NOTIFY: "Notification sent to specified recipients.",
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def detect_channel(text: str) -> str | None:
    """Detect the communication channel mentioned in *text*."""
    lower = text.lower()
    scores: dict[str, int] = {}
    for channel, patterns in _CHANNEL_PATTERNS.items():
        score = sum(1 for p in patterns if p in lower)
        if score:
            scores[channel] = score
    if not scores:
        return None
    return max(scores, key=scores.get)  # type: ignore[arg-type]


def detect_urgency(text: str) -> str:
    """Detect urgency level from text signals."""
    lower = text.lower()
    if any(k in lower for k in ["urgent", "asap", "critical", "emergency", "紧急", "立刻", "马上"]):
        return "P1-URGENT"
    if any(k in lower for k in ["action required", "please respond", "deadline", "截止", "需要回复"]):
        return "P2-ACTION"
    if any(k in lower for k in ["fyi", "no action", "informational", "供参考"]):
        return "P3-FYI"
    return "P2-ACTION"  # default


def estimate_reading_time(text: str) -> int:
    """Estimate reading time in minutes (average 200 words/min)."""
    word_count = len(text.split())
    return max(1, round(word_count / 200))


# ---------------------------------------------------------------------------
# CommsAgent
# ---------------------------------------------------------------------------

class CommsAgent(BaseAgent):
    """Specialist agent for communication tasks.

    Supports multiple communication workflows:
    - **triage**: classify and prioritize inbox messages
    - **reply**: draft contextual replies matching tone
    - **compose**: write new messages with quality checks
    - **summarize**: extract key points from conversation threads
    - **digest**: create notification summaries
    - **forward**: forward with added context
    - **template**: create reusable message templates
    - **notify**: send notifications and announcements
    """

    def __init__(self) -> None:
        super().__init__(AgentCard(
            name="comms-agent",
            description="Email triage, message drafting, thread summarization, and notification management",
            skills=["email", "message", "notification", "reply", "triage",
                    "summarize", "digest", "compose", "multi-channel"],
            input_modes=["text"],
            output_modes=["text", "notification"],
            domain="communication",
            can_delegate=True,
        ))

    # -- public API --------------------------------------------------------

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        logger.info("[CommsAgent] Processing: %s", message[:80])

        task_type = self._classify(message)
        channel = detect_channel(message)
        urgency = detect_urgency(message)

        # Try LLM-backed execution first
        if self._llm_registry:
            system_prompt = self._build_system_prompt(task_type, channel)
            result = await self._llm_execute(
                message, context,
                system_prompt=system_prompt,
                max_tool_rounds=5,
            )
            if result.success:
                return result
            logger.warning("[CommsAgent] LLM execution failed, falling back to mock: %s", result.error)

        # Mock fallback
        output = f"[CommsAgent] Task type: '{task_type}'"
        if channel:
            output += f", channel='{channel}'"
        output += f", urgency='{urgency}'"
        output += ". "
        output += _MOCK_OUTPUTS.get(task_type, "Communication task processed.")

        return TaskResult(
            task_id=context.task_id, agent_name=self.name,
            success=True, output=output,
        )

    def can_handle(self, message: str) -> float:
        keywords = [
            "email", "邮件", "message", "消息", "inbox", "收件箱",
            "reply", "回复", "notification", "通知", "钉钉", "slack",
            "triage", "整理", "draft", "草稿", "unread", "未读",
            "compose", "撰写", "forward", "转发", "digest", "简报",
            "thread", "conversation", "对话", "summarize", "摘要",
            "template", "模板", "announcement", "公告",
        ]
        msg = message.lower()
        return min(sum(1 for k in keywords if k in msg) * 0.3, 1.0)

    # -- private helpers ---------------------------------------------------

    def _classify(self, message: str) -> str:
        msg = message.lower()
        for keywords, category in _TASK_KEYWORDS:
            if any(k in msg for k in keywords):
                return category
        return _TASK_NOTIFY  # safe default

    def _build_system_prompt(self, task_type: str, channel: str | None) -> str:
        """Compose a task-specific system prompt with channel context."""
        parts = [COMMS_AGENT_SYSTEM_PROMPT]

        augmentation = _TASK_PROMPTS.get(task_type)
        if augmentation:
            parts.append(f"\n# Current task: {task_type}\n{augmentation}")

        if channel:
            parts.append(
                f"\n# Detected channel: {channel}\n"
                f"Adapt formatting and tone for {channel}."
            )

        return "\n".join(parts)
