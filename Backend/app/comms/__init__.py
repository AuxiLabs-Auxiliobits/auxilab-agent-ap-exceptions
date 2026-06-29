"""Outbound communications — send drafts via Gmail SMTP or Slack webhook.

Sending is ALWAYS triggered by an explicit human action (POST .../send).
There is no auto-send path anywhere in the system.
"""
from app.comms.dispatcher import SendResult, dispatch

__all__ = ["SendResult", "dispatch"]
