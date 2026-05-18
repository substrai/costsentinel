"""Tests for alert notifier."""

import time
import tempfile
from pathlib import Path

from costsentinel.detection.anomaly import AnomalyAlert
from costsentinel.alerts.notifier import AlertNotifier, AlertChannel, NotificationRecord


class TestAlertNotifier:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.notifier = AlertNotifier(
            channels=[AlertChannel(type="log", severity_filter=["critical", "warning"])],
            history_path=self.tmp.name,
            cooldown_seconds=0,  # Disable cooldown for tests
        )

    def teardown_method(self):
        Path(self.tmp.name).unlink(missing_ok=True)

    def _make_alert(self, severity="critical") -> AnomalyAlert:
        return AnomalyAlert(
            alert_type="cost_spike",
            severity=severity,
            scope_key="test:scope",
            message="Test alert",
            current_value=1.0,
            baseline_value=0.5,
            multiplier=2.0,
            timestamp=time.time(),
        )

    def test_notify_sends_to_matching_channels(self):
        alert = self._make_alert("critical")
        records = self.notifier.notify(alert)
        assert len(records) == 1
        assert records[0].success is True

    def test_notify_filters_by_severity(self):
        alert = self._make_alert("info")
        records = self.notifier.notify(alert)
        assert len(records) == 0  # "info" not in severity_filter

    def test_notify_records_in_history(self):
        alert = self._make_alert("warning")
        self.notifier.notify(alert)
        history = self.notifier.get_history()
        assert len(history) == 1

    def test_cooldown_prevents_duplicates(self):
        notifier = AlertNotifier(
            channels=[AlertChannel(type="log")],
            history_path=self.tmp.name,
            cooldown_seconds=60.0,
        )
        alert = self._make_alert("critical")
        records1 = notifier.notify(alert)
        records2 = notifier.notify(alert)  # Should be suppressed
        assert len(records1) == 1
        assert len(records2) == 0

    def test_different_alerts_not_cooled_down(self):
        notifier = AlertNotifier(
            channels=[AlertChannel(type="log")],
            history_path=self.tmp.name,
            cooldown_seconds=60.0,
        )
        alert1 = AnomalyAlert(
            alert_type="cost_spike", severity="critical", scope_key="scope:a",
            message="A", current_value=1.0, baseline_value=0.5, multiplier=2.0,
        )
        alert2 = AnomalyAlert(
            alert_type="cost_spike", severity="critical", scope_key="scope:b",
            message="B", current_value=1.0, baseline_value=0.5, multiplier=2.0,
        )
        records1 = notifier.notify(alert1)
        records2 = notifier.notify(alert2)
        assert len(records1) == 1
        assert len(records2) == 1

    def test_multiple_channels(self):
        notifier = AlertNotifier(
            channels=[
                AlertChannel(type="log", severity_filter=["critical"]),
                AlertChannel(type="log", severity_filter=["critical", "warning"]),
            ],
            history_path=self.tmp.name,
            cooldown_seconds=0,
        )
        alert = self._make_alert("critical")
        records = notifier.notify(alert)
        assert len(records) == 2

    def test_notification_record_fields(self):
        alert = self._make_alert("critical")
        records = self.notifier.notify(alert)
        record = records[0]
        assert record.alert_type == "cost_spike"
        assert record.severity == "critical"
        assert record.channel_type == "log"
        assert record.success is True
        assert record.timestamp > 0

    def test_format_message_contains_info(self):
        alert = self._make_alert("warning")
        records = self.notifier.notify(alert)
        assert "WARNING" in records[0].message
        assert "cost_spike" in records[0].message
