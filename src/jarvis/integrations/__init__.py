"""External service integration adapters for JARVIS.

Provides clients for GitHub, Slack, Jira, generic webhooks, and a
calendar service abstraction.
"""

from jarvis.integrations.calendar_service import CalendarEvent, CalendarService
from jarvis.integrations.github import (
    GitHubClient,
    GitHubConfig,
    GitHubIssue,
    GitHubPR,
    GitHubRepo,
)
from jarvis.integrations.jira import JiraClient, JiraConfig, JiraIssue, build_jql
from jarvis.integrations.slack import SlackClient, SlackConfig, SlackMessage
from jarvis.integrations.webhook import WebhookClient, WebhookConfig

__all__ = [
    # GitHub
    "GitHubClient",
    "GitHubConfig",
    "GitHubIssue",
    "GitHubPR",
    "GitHubRepo",
    # Slack
    "SlackClient",
    "SlackConfig",
    "SlackMessage",
    # Jira
    "JiraClient",
    "JiraConfig",
    "JiraIssue",
    "build_jql",
    # Webhook
    "WebhookClient",
    "WebhookConfig",
    # Calendar
    "CalendarEvent",
    "CalendarService",
]
