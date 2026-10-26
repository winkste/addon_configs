"""
AppDaemon Class: BatteryMonitor
Author: AI Collaborator
Version: 1.0

Description:
    Daily battery level check for all battery powered devices:
    1. Discovery: Finds all sensors with device_class "battery" automatically
       (numeric sensors in % and binary low battery sensors).
    2. Threshold: Collects every sensor below the configured threshold.
    3. Notification: Creates one persistent notification with the sorted list.
       If all batteries are ok, an old notification is dismissed.
    4. Exclude (Optional): A list of entities that are never reported.
"""

import appdaemon.plugins.hass.hassapi as hass

NOTIFICATION_ID = "battery_monitor"


class BatteryMonitor(hass.Hass):
    """Checks battery levels once a day and reports low batteries via persistent notification."""

    def initialize(self):
        """Initialize the App and schedule the daily check."""
        # Load configuration arguments
        self.threshold = self.args.get("threshold", 20)
        self.check_time = self.args.get("check_time", "09:00:00")
        self.exclude = self.args.get("exclude", [])

        self.run_daily(self.check_callback, self.check_time)
        self.log(f"Battery Monitor scheduled at {self.check_time} (threshold {self.threshold} %).")

    def check_callback(self, kwargs):
        """Collect low batteries and update the persistent notification."""
        low_batteries = self._get_low_batteries()
        if not low_batteries:
            self.log("All batteries above threshold.")
            self.call_service("persistent_notification/dismiss", notification_id=NOTIFICATION_ID)
            return

        self.log(f"{len(low_batteries)} low batteries found.")
        self._send_notification(low_batteries)

    def _get_low_batteries(self):
        """Return a list of (name, level, label) tuples sorted by level, lowest first."""
        low_batteries = []
        low_batteries.extend(self._get_low_numeric_batteries())
        low_batteries.extend(self._get_low_binary_batteries())
        return sorted(low_batteries, key=lambda item: item[1])

    def _get_low_numeric_batteries(self):
        """Return numeric battery sensors (in %) below the threshold."""
        result = []
        for entity, state in self._get_battery_entities("sensor").items():
            try:
                level = float(state["state"])
            except (TypeError, ValueError):
                # unavailable / unknown states are ignored
                continue
            if level < self.threshold:
                result.append((self._get_name(entity, state), level, f"{level:.0f} %"))
        return result

    def _get_low_binary_batteries(self):
        """Return binary battery sensors reporting low battery (state on)."""
        result = []
        for entity, state in self._get_battery_entities("binary_sensor").items():
            if state["state"] == "on":
                # level 0 sorts binary low batteries to the top of the list
                result.append((self._get_name(entity, state), 0, "low"))
        return result

    def _get_battery_entities(self, domain):
        """Return all non excluded entities of a domain with device_class battery."""
        states = self.get_state(domain) or {}
        return {
            entity: state
            for entity, state in states.items()
            if state.get("attributes", {}).get("device_class") == "battery"
            and entity not in self.exclude
        }

    def _get_name(self, entity, state):
        """Return the friendly name of an entity, fallback to the entity id."""
        return state.get("attributes", {}).get("friendly_name", entity)

    def _send_notification(self, low_batteries):
        """Create or replace the persistent notification with the low battery list."""
        lines = [f"- {name}: {label}" for name, _, label in low_batteries]

        self.call_service(
            "persistent_notification/create",
            notification_id=NOTIFICATION_ID,
            title=f"Low battery ({len(low_batteries)})",
            message=f"Below {self.threshold} %:\n" + "\n".join(lines),
        )
