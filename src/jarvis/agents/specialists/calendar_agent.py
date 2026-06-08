from __future__ import annotations

import logging
import re
from typing import Any

from jarvis.agents.base import AgentCard, AgentContext, BaseAgent, TaskResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt -- comprehensive calendar and scheduling specialist
# ---------------------------------------------------------------------------

CALENDAR_AGENT_SYSTEM_PROMPT = """\
You are a calendar and scheduling specialist within the JARVIS assistant system.

# Capabilities
- Schedule management and event creation / modification / deletion
- Conflict detection and resolution across multiple calendars
- Meeting preparation (agenda drafting, document gathering, attendee briefing)
- Reminder and notification management
- Recurring event pattern handling (daily, weekly, monthly, yearly, custom)
- Timezone-aware scheduling for distributed teams
- Calendar analytics (meeting load, free time, focus time analysis)

You have access to tools: read_file, write_file, python_execute, shell_execute.
Use them to inspect calendars, compute time slots, and generate structured output.

# Execution protocol
1. **Parse** -- extract date, time, duration, timezone, attendees from the request.
2. **Validate** -- check parsed values; ask for clarification if ambiguous.
3. **Check conflicts** -- query existing calendar for overlapping events.
4. **Resolve** -- propose alternative slots if conflicts exist.
5. **Execute** -- create/modify/delete the event in structured format.
6. **Confirm** -- output a summary with all event details.

# Time parsing hints
When interpreting natural language dates and times:
- "tomorrow" = current date + 1 day
- "next Monday" = the coming Monday (skip today if already Monday)
- "in 2 hours" = current time + 2h
- "end of day" = 17:00 in the user's timezone
- "morning" = 09:00-12:00, "afternoon" = 13:00-17:00, "evening" = 18:00-21:00
- Ambiguous times: prefer business hours (09:00-17:00) unless context suggests otherwise
- If no timezone specified, default to the user's configured timezone (fallback: UTC)

# Timezone handling
- Always store events in UTC internally
- Display in the user's local timezone
- For multi-timezone meetings, show each attendee's local time
- Common abbreviations: PST=-8, EST=-5, CST=-6, MST=-7, IST=+5:30, JST=+9, CET=+1, CST_CN=+8
- Daylight saving: be aware of DST transitions (PST->PDT, EST->EDT, etc.)
- Use IANA timezone names when possible (America/Los_Angeles, Asia/Shanghai)

# Conflict detection and resolution strategies
When checking for conflicts:
1. **Hard conflicts** -- exact overlap with non-movable events (e.g., external meetings)
2. **Soft conflicts** -- overlap with movable/optional events
3. **Buffer conflicts** -- insufficient travel/transition time between events

Resolution strategies (in priority order):
1. Suggest the nearest free slot on the same day
2. If same-day is full, suggest the next available day
3. If attendees have different availability, propose top-3 slots
4. For recurring conflicts, suggest permanent reschedule
5. Allow the user to override with explicit confirmation

# Recurring event patterns
Support these recurrence types:
- DAILY: every N days
- WEEKLY: every N weeks on specified weekdays
- MONTHLY: Nth weekday of month, or specific date
- YEARLY: specific month and day
- CUSTOM: complex patterns (e.g., "every other Tuesday", "last Friday of month")
- EXCEPTION: skip specific dates in a recurrence series
- END: by count (after N occurrences) or by date (until YYYY-MM-DD)

# Multiple calendar backend awareness
Be prepared to work with different calendar systems:
- Google Calendar (primary)
- Microsoft Outlook / Exchange
- Apple Calendar (iCal/CalDAV)
- CalDAV-compatible servers
- ICS file import/export

Normalize event data to a common format regardless of backend.

# Meeting preparation workflow
When preparing for a meeting:
1. **Agenda** -- draft structured agenda with time allocations per topic
2. **Documents** -- identify and gather relevant files, reports, and links
3. **Attendees** -- list attendees with roles and talking points
4. **Pre-read** -- compile any materials attendees should review beforehand
5. **Follow-up** -- template for action items and meeting notes
6. **Reminder** -- set pre-meeting reminder (default: 15 min before)

# Structured event output format
Always output events in this structured format:
```
Event: {title}
Date: {YYYY-MM-DD}
Time: {HH:MM} - {HH:MM} ({timezone})
Duration: {N} minutes
Location: {physical address or virtual link}
Attendees: {comma-separated list}
Recurrence: {pattern or "none"}
Reminder: {N minutes before}
Description: {brief description}
Status: {confirmed/tentative/cancelled}
```

# Calendar analytics
When asked about meeting load or schedule analysis:
- Compute total meeting hours per day/week
- Identify focus time blocks (>= 2 hours uninterrupted)
- Flag meeting-heavy days (>6 hours of meetings)
- Suggest schedule optimization (batch similar meetings, protect focus time)
- Track meeting patterns over time
"""

# ---------------------------------------------------------------------------
# Time-related parsing patterns
# ---------------------------------------------------------------------------

_TIME_PATTERNS: dict[str, list[str]] = {
    "morning": ["morning", "am", "早上", "上午", "早晨"],
    "afternoon": ["afternoon", "pm", "下午"],
    "evening": ["evening", "晚上", "傍晚"],
    "night": ["night", "夜里", "深夜"],
}

_TIMEZONE_ALIASES: dict[str, str] = {
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "est": "America/New_York",
    "edt": "America/New_York",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "mst": "America/Denver",
    "mdt": "America/Denver",
    "utc": "UTC",
    "gmt": "UTC",
    "ist": "Asia/Kolkata",
    "jst": "Asia/Tokyo",
    "kst": "Asia/Seoul",
    "cet": "Europe/Berlin",
    "cest": "Europe/Berlin",
    "bst": "Europe/London",
    "aest": "Australia/Sydney",
    "cst_cn": "Asia/Shanghai",
    "beijing": "Asia/Shanghai",
    "北京时间": "Asia/Shanghai",
    "东八区": "Asia/Shanghai",
}

# ---------------------------------------------------------------------------
# Task type definitions
# ---------------------------------------------------------------------------

_TASK_SCHEDULE = "schedule"
_TASK_CONFLICT = "conflict"
_TASK_REMINDER = "reminder"
_TASK_MEETING_PREP = "meeting-prep"
_TASK_RECURRING = "recurring"
_TASK_ANALYTICS = "analytics"
_TASK_MODIFY = "modify"
_TASK_CANCEL = "cancel"

_TASK_KEYWORDS: list[tuple[list[str], str]] = [
    (["conflict", "冲突", "overlap", "重叠", "clash", "double-booked"], _TASK_CONFLICT),
    (["remind", "提醒", "alarm", "闹钟", "notification", "通知"], _TASK_REMINDER),
    (["prep", "准备", "agenda", "议程", "pre-read", "briefing", "brief"], _TASK_MEETING_PREP),
    (["recurring", "重复", "repeat", "every week", "每周", "every day", "每天", "every month", "每月"], _TASK_RECURRING),
    (["analytics", "分析", "meeting load", "会议负荷", "focus time", "专注时间", "how many meetings", "多少会议"], _TASK_ANALYTICS),
    (["modify", "修改", "change", "更改", "update", "更新", "reschedule", "改期", "move"], _TASK_MODIFY),
    (["cancel", "取消", "delete", "删除", "remove", "移除"], _TASK_CANCEL),
    (["schedule", "安排", "book", "预约", "create", "创建", "set up", "plan", "计划", "add event", "新建"], _TASK_SCHEDULE),
]

# ---------------------------------------------------------------------------
# Task-specific prompt augmentations
# ---------------------------------------------------------------------------

_TASK_PROMPTS: dict[str, str] = {
    _TASK_SCHEDULE: (
        "You are creating a new calendar event. "
        "Extract: title, date, time, duration, timezone, location, attendees. "
        "Check for conflicts before confirming. Output in structured event format."
    ),
    _TASK_CONFLICT: (
        "You are resolving a scheduling conflict. "
        "List all conflicting events with times. "
        "Propose 3 alternative time slots, ranked by suitability. "
        "Consider attendee availability and buffer time."
    ),
    _TASK_REMINDER: (
        "You are setting a reminder or notification. "
        "Parse when the reminder should fire (absolute time or relative offset). "
        "Confirm the reminder details with the user."
    ),
    _TASK_MEETING_PREP: (
        "You are preparing for a meeting. Follow the meeting preparation workflow:\n"
        "1. Draft a structured agenda with time allocations.\n"
        "2. List attendees and their expected contributions.\n"
        "3. Identify documents or materials to gather.\n"
        "4. Prepare pre-read materials.\n"
        "5. Create an action items template."
    ),
    _TASK_RECURRING: (
        "You are setting up a recurring event. "
        "Parse the recurrence pattern (daily, weekly, monthly, custom). "
        "Specify: frequency, day-of-week, end condition. "
        "Check for recurring conflicts across the series."
    ),
    _TASK_ANALYTICS: (
        "You are analyzing meeting/calendar patterns. "
        "Compute total meeting hours, free blocks, meeting density. "
        "Identify schedule optimization opportunities. "
        "Present findings in a summary with actionable suggestions."
    ),
    _TASK_MODIFY: (
        "You are modifying an existing event. "
        "Identify which event to modify and what fields to change. "
        "Check for new conflicts after the change. "
        "Output the updated event in structured format."
    ),
    _TASK_CANCEL: (
        "You are cancelling/deleting an event. "
        "Identify which event to cancel. "
        "If recurring, ask whether to cancel this occurrence or the entire series. "
        "Confirm the cancellation with the user."
    ),
}

# ---------------------------------------------------------------------------
# Mock outputs per task type
# ---------------------------------------------------------------------------

_MOCK_OUTPUTS: dict[str, str] = {
    _TASK_SCHEDULE: (
        "Event created:\n"
        "  Title: Team Sync\n"
        "  Date: 2024-01-15\n"
        "  Time: 14:00-14:30 (UTC+8)\n"
        "  Duration: 30 minutes\n"
        "  Location: Zoom\n"
        "  Status: confirmed"
    ),
    _TASK_CONFLICT: (
        "Conflict detected: existing meeting at 14:00.\n"
        "Alternative slots proposed:\n"
        "  1. 15:00-15:30 (same day)\n"
        "  2. 10:00-10:30 (same day)\n"
        "  3. 14:00-14:30 (next day)"
    ),
    _TASK_REMINDER: "Reminder set for the specified time.",
    _TASK_MEETING_PREP: (
        "Meeting preparation complete:\n"
        "  Agenda: 3 topics (15+20+10 min)\n"
        "  Attendees: 5 confirmed\n"
        "  Pre-read: 2 documents attached\n"
        "  Action items template created"
    ),
    _TASK_RECURRING: "Recurring event created: every Tuesday at 10:00 for 12 weeks.",
    _TASK_ANALYTICS: (
        "Calendar analytics:\n"
        "  Total meetings this week: 18 (13.5 hours)\n"
        "  Focus time blocks: 3 (6.5 hours)\n"
        "  Busiest day: Wednesday (5 meetings)\n"
        "  Suggestion: protect Thursday morning for deep work"
    ),
    _TASK_MODIFY: "Event updated successfully. No new conflicts detected.",
    _TASK_CANCEL: "Event cancelled. Attendees notified.",
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def detect_time_of_day(text: str) -> str | None:
    """Detect the time-of-day reference in *text*."""
    lower = text.lower()
    for period, patterns in _TIME_PATTERNS.items():
        if any(p in lower for p in patterns):
            return period
    return None


def resolve_timezone(text: str) -> str | None:
    """Resolve a timezone alias from *text* to IANA name."""
    lower = text.lower()
    for alias, iana in _TIMEZONE_ALIASES.items():
        if alias in lower:
            return iana
    return None


def parse_duration_minutes(text: str) -> int | None:
    """Extract a duration in minutes from natural-language *text*."""
    lower = text.lower()
    # "30 minutes", "1 hour", "1.5 hours", "90 min"
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:hours?|小时|hrs?)", lower)
    if match:
        return int(float(match.group(1)) * 60)
    match = re.search(r"(\d+)\s*(?:minutes?|分钟|mins?|min)", lower)
    if match:
        return int(match.group(1))
    return None


# ---------------------------------------------------------------------------
# CalendarAgent
# ---------------------------------------------------------------------------

class CalendarAgent(BaseAgent):
    """Specialist agent for calendar and scheduling tasks.

    Supports multiple scheduling workflows:
    - **schedule**: create new events with conflict checking
    - **conflict**: detect and resolve scheduling conflicts
    - **reminder**: set reminders and notifications
    - **meeting-prep**: prepare agendas, docs, attendee briefings
    - **recurring**: set up recurring event patterns
    - **analytics**: analyze meeting load and schedule patterns
    - **modify**: update existing events
    - **cancel**: remove events from calendar
    """

    def __init__(self) -> None:
        super().__init__(AgentCard(
            name="calendar-agent",
            description="Schedule management, conflict detection, meeting preparation, and calendar analytics",
            skills=["schedule", "calendar", "meeting", "reminder", "conflict-detection",
                    "recurring-events", "timezone", "meeting-prep", "calendar-analytics"],
            input_modes=["text", "structured-data"],
            output_modes=["text", "calendar-event", "notification"],
            domain="personal-productivity",
            can_delegate=True,
        ))

    # -- public API --------------------------------------------------------

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        logger.info("[CalendarAgent] Processing: %s", message[:80])

        task_type = self._classify(message)
        timezone = resolve_timezone(message)
        time_of_day = detect_time_of_day(message)
        duration = parse_duration_minutes(message)

        # Try LLM-backed execution first
        if self._llm_registry:
            system_prompt = self._build_system_prompt(task_type, timezone, time_of_day)
            result = await self._llm_execute(
                message, context,
                system_prompt=system_prompt,
                max_tool_rounds=5,
            )
            if result.success:
                return result
            logger.warning("[CalendarAgent] LLM execution failed, falling back to mock: %s", result.error)

        # Mock fallback
        output = f"[CalendarAgent] Task type: '{task_type}'"
        if timezone:
            output += f", timezone='{timezone}'"
        if time_of_day:
            output += f", time_of_day='{time_of_day}'"
        if duration:
            output += f", duration={duration}min"
        output += ". "
        output += _MOCK_OUTPUTS.get(task_type, "Calendar task processed.")

        return TaskResult(
            task_id=context.task_id, agent_name=self.name,
            success=True, output=output,
        )

    def can_handle(self, message: str) -> float:
        keywords = [
            "calendar", "日历", "schedule", "日程", "meeting", "会议",
            "appointment", "remind", "提醒", "event", "活动",
            "conflict", "冲突", "agenda", "议程", "book", "预约",
            "recurring", "重复", "timezone", "时区", "focus time",
            "reschedule", "改期", "cancel meeting", "取消会议",
            "free slot", "空闲", "available", "可用时间",
        ]
        msg = message.lower()
        return min(sum(1 for k in keywords if k in msg) * 0.3, 1.0)

    # -- private helpers ---------------------------------------------------

    def _classify(self, message: str) -> str:
        msg = message.lower()
        for keywords, category in _TASK_KEYWORDS:
            if any(k in msg for k in keywords):
                return category
        return _TASK_SCHEDULE  # safe default

    def _build_system_prompt(self, task_type: str, timezone: str | None, time_of_day: str | None) -> str:
        """Compose a task-specific system prompt with optional timezone context."""
        parts = [CALENDAR_AGENT_SYSTEM_PROMPT]

        augmentation = _TASK_PROMPTS.get(task_type)
        if augmentation:
            parts.append(f"\n# Current task: {task_type}\n{augmentation}")

        if timezone:
            parts.append(f"\n# Detected timezone: {timezone}\nUse this timezone for display.")

        if time_of_day:
            parts.append(f"\n# Time of day: {time_of_day}\nInterpret time references accordingly.")

        return "\n".join(parts)
