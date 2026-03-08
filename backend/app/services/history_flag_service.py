from __future__ import annotations

from app.schemas import DerivedHistoryFlags, RawCallHistory


class HistoryFlagService:
    def derive_flags(self, *, call_history: RawCallHistory) -> DerivedHistoryFlags:
        frequent_caller = call_history.total_calls_last_30d >= 7
        recent_urgent_pattern = call_history.urgent_calls_last_30d >= 2
        repeated_false_alarms = call_history.false_alarm_count_last_30d >= 3
        escalation_ratio = (
            call_history.urgent_calls_last_30d / call_history.total_calls_last_30d
            if call_history.total_calls_last_30d > 0
            else 0.0
        )
        escalation_trend = call_history.total_calls_last_30d >= 5 and escalation_ratio >= 0.3

        evidence: list[str] = []
        if frequent_caller:
            evidence.append("high recent call volume (>=7 in last 30 days)")
        if recent_urgent_pattern:
            evidence.append("multiple recent urgent incidents")
        if repeated_false_alarms:
            evidence.append("repeated false alarms suggest signal ambiguity")
        if escalation_trend:
            evidence.append("urgent call ratio indicates possible escalation trend")

        return DerivedHistoryFlags(
            frequent_caller=frequent_caller,
            recent_urgent_pattern=recent_urgent_pattern,
            repeated_false_alarms=repeated_false_alarms,
            escalation_trend=escalation_trend,
            evidence=evidence,
        )

