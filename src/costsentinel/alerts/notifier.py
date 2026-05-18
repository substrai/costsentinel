"""Multi-channel alert notification system."""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from costsentinel.detection.anomaly import AnomalyAlert

logger = logging.getLogger(__name__)


@dataclass
class AlertChannel:
    """Configuration for an alert notification channel."""

    type: str  # sns | slack | webhook | log
    config: Dict[str, Any] = field(default_factory=dict)
    severity_filter: List[str] = field(default_factory=lambda: ["critical", "warning"])


@dataclass
class NotificationRecord:
    """Record of a sent notification."""

    alert_type: str
    severity: str
    channel_type: str
    message: str
    timestamp: float
    success: bool
    error: Optional[str] = None


class AlertNotifier:
    """Sends alert notifications to configured channels.

    Supports multiple channels: Slack webhooks, generic webhooks,
    SNS (requires boto3), and local logging.
    """

    def __init__(
        self,
        channels: Optional[List[AlertChannel]] = None,
        history_path: str | Path = ".costsentinel_alerts_history.json",
        cooldown_seconds: float = 300.0,
    ):
        """Initialize alert notifier.

        Args:
            channels: List of alert channels. Defaults to log-only.
            history_path: Path to notification history file.
            cooldown_seconds: Minimum seconds between duplicate alerts.
        """
        self.channels = channels or [AlertChannel(type="log")]
        self.history_path = Path(history_path)
        self.cooldown_seconds = cooldown_seconds
        self._history: List[NotificationRecord] = []
        self._last_alert_times: Dict[str, float] = {}

    def notify(self, alert: AnomalyAlert) -> List[NotificationRecord]:
        """Send alert to all matching channels.

        Args:
            alert: The anomaly alert to send.

        Returns:
            List of notification records (one per channel attempted).
        """
        # Check cooldown
        alert_key = f"{alert.alert_type}:{alert.scope_key}"
        now = time.time()
        last_time = self._last_alert_times.get(alert_key, 0.0)
        if now - last_time < self.cooldown_seconds:
            return []

        self._last_alert_times[alert_key] = now
        records: List[NotificationRecord] = []

        for channel in self.channels:
            if alert.severity not in channel.severity_filter:
                continue

            record = self._send_to_channel(alert, channel)
            records.append(record)
            self._history.append(record)

        self._save_history()
        return records

    def _send_to_channel(self, alert: AnomalyAlert, channel: AlertChannel) -> NotificationRecord:
        """Send alert to a specific channel."""
        message = self._format_message(alert)

        try:
            if channel.type == "log":
                self._send_log(alert, message)
            elif channel.type == "slack":
                self._send_slack(alert, message, channel.config)
            elif channel.type == "webhook":
                self._send_webhook(alert, message, channel.config)
            elif channel.type == "sns":
                self._send_sns(alert, message, channel.config)
            else:
                logger.warning(f"Unknown channel type: {channel.type}")

            return NotificationRecord(
                alert_type=alert.alert_type,
                severity=alert.severity,
                channel_type=channel.type,
                message=message,
                timestamp=time.time(),
                success=True,
            )
        except Exception as e:
            return NotificationRecord(
                alert_type=alert.alert_type,
                severity=alert.severity,
                channel_type=channel.type,
                message=message,
                timestamp=time.time(),
                success=False,
                error=str(e),
            )

    def _format_message(self, alert: AnomalyAlert) -> str:
        """Format alert into human-readable message."""
        return (
            f"[{alert.severity.upper()}] {alert.alert_type}: {alert.message} "
            f"(current={alert.current_value:.4f}, baseline={alert.baseline_value:.4f}, "
            f"{alert.multiplier:.1f}x)"
        )

    def _send_log(self, alert: AnomalyAlert, message: str) -> None:
        """Send alert to Python logger."""
        if alert.severity == "critical":
            logger.critical(message)
        elif alert.severity == "warning":
            logger.warning(message)
        else:
            logger.info(message)

    def _send_slack(self, alert: AnomalyAlert, message: str, config: Dict[str, Any]) -> None:
        """Send alert to Slack webhook."""
        webhook_url = config.get("webhook_url", "")
        if not webhook_url:
            raise ValueError("Slack webhook_url not configured")

        payload = json.dumps({"text": message}).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)

    def _send_webhook(self, alert: AnomalyAlert, message: str, config: Dict[str, Any]) -> None:
        """Send alert to generic webhook."""
        url = config.get("url", "")
        if not url:
            raise ValueError("Webhook URL not configured")

        payload = json.dumps({
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "scope_key": alert.scope_key,
            "message": message,
            "current_value": alert.current_value,
            "baseline_value": alert.baseline_value,
            "multiplier": alert.multiplier,
            "timestamp": alert.timestamp,
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)

    def _send_sns(self, alert: AnomalyAlert, message: str, config: Dict[str, Any]) -> None:
        """Send alert to AWS SNS topic."""
        try:
            import boto3
        except ImportError:
            raise ImportError("boto3 required for SNS alerts: pip install substrai-costsentinel[aws]")

        topic_arn = config.get("topic_arn", "")
        if not topic_arn:
            raise ValueError("SNS topic_arn not configured")

        sns = boto3.client("sns")
        sns.publish(
            TopicArn=topic_arn,
            Subject=f"CostSentinel [{alert.severity.upper()}]: {alert.alert_type}",
            Message=message,
        )

    def _save_history(self) -> None:
        """Save notification history."""
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "alert_type": r.alert_type,
                "severity": r.severity,
                "channel_type": r.channel_type,
                "message": r.message,
                "timestamp": r.timestamp,
                "success": r.success,
                "error": r.error,
            }
            for r in self._history[-100:]  # Keep last 100
        ]
        with open(self.history_path, "w") as f:
            json.dump(data, f)

    def get_history(self) -> List[NotificationRecord]:
        """Get notification history."""
        return list(self._history)
