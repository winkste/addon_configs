"""
AppDaemon Classes: WaterAlarm, SmokeAlarm
Author: AI Collaborator
Version: 1.0

Description:
    Notification on detector alarms (water leakage, smoke):
    1. Alarm: Creates a persistent notification per detector when it triggers,
       including the Home Assistant area of the sensor.
    2. Clear: Keeps the notification and adds the time the alarm was cleared.
    3. Unavailable: Creates a separate notification if a detector is unavailable
       for a configured time and dismisses it once the detector is back.
    4. Push (Optional): Sends the messages also to the listed notify services,
       either as normal push or as iOS critical alert (sound even if muted).

Args:
    sensor: list of binary sensors to monitor
    push: optional list of notify services for normal push messages
    critical_push: optional list of notify services for critical alarm push messages
    unavailable_delay: seconds a detector has to be unavailable before reporting (default 3600)
"""

import appdaemon.plugins.hass.hassapi as hass

CRITICAL_PUSH_DATA = {"push": {"sound": {"name": "default", "critical": 1, "volume": 1.0}}}


class AlarmNotifier(hass.Hass):
    """Base class for detector alarm notifications, subclasses define the alarm type."""

    ALARM_TYPE = "Alarm"

    def initialize(self):
        """Initialize the App and subscribe to the detector state changes."""
        # Load configuration arguments
        self.sensors = self.args.get("sensor", [])
        self.push = self.args.get("push", [])
        self.critical_push = self.args.get("critical_push", [])
        self.unavailable_delay = self.args.get("unavailable_delay", 3600)

        # Runtime variables
        self.trigger_times = {}

        if not self.sensors:
            self.error("No sensor specified. The app has nothing to monitor.")
            return

        for sensor in self.sensors:
            self.listen_state(self.alarm_on_callback, sensor, new="on")
            self.listen_state(self.alarm_off_callback, sensor, old="on", new="off")
            self.listen_state(
                self.unavailable_callback, sensor, new="unavailable", duration=self.unavailable_delay
            )
            self.listen_state(self.available_callback, sensor, old="unavailable")

        self.log(f"{self.ALARM_TYPE} notifier monitoring {len(self.sensors)} sensors.")

    def alarm_on_callback(self, entity, attribute, old, new, kwargs):
        """Handle a triggered detector."""
        trigger_time = self._get_time()
        self.trigger_times[entity] = trigger_time
        message = f"{self._get_name(entity)} triggered at {trigger_time}."

        self.log(f"{self.ALARM_TYPE} triggered on {entity}", level="WARNING")
        self._create_notification(f"{entity}_alarm", self.ALARM_TYPE, message)
        self._send_push(self.ALARM_TYPE, message, self.push)
        self._send_push(self.ALARM_TYPE, message, self.critical_push, critical=True)

    def alarm_off_callback(self, entity, attribute, old, new, kwargs):
        """Handle a cleared detector, keep the alarm notification and add the clear time."""
        trigger_time = self.trigger_times.pop(entity, "unknown time")
        clear_time = self._get_time()
        title = f"{self.ALARM_TYPE} cleared"
        message = f"{self._get_name(entity)} triggered at {trigger_time}, cleared at {clear_time}."

        self.log(f"{self.ALARM_TYPE} cleared on {entity}")
        self._create_notification(f"{entity}_alarm", title, message)
        # clear messages are never sent as critical alert
        self._send_push(title, message, self.push + self.critical_push)

    def unavailable_callback(self, entity, attribute, old, new, kwargs):
        """Handle a detector that is unavailable for the configured time."""
        title = "Detector unavailable"
        message = (
            f"{self._get_name(entity)} is unavailable since "
            f"{self.unavailable_delay // 60} minutes. {self.ALARM_TYPE} detection is not working."
        )

        self.log(f"{entity} unavailable for {self.unavailable_delay} seconds", level="WARNING")
        self._create_notification(f"{entity}_unavailable", title, message)
        self._send_push(title, message, self.push + self.critical_push)

    def available_callback(self, entity, attribute, old, new, kwargs):
        """Dismiss the unavailable notification once the detector is back."""
        self.log(f"{entity} available again")
        self.call_service(
            "persistent_notification/dismiss", notification_id=f"{entity}_unavailable"
        )

    def _create_notification(self, notification_id, title, message):
        """Create or replace a persistent notification."""
        self.call_service(
            "persistent_notification/create",
            notification_id=notification_id,
            title=title,
            message=message,
        )

    def _send_push(self, title, message, services, critical=False):
        """Send a push message to all given notify services."""
        for service in services:
            service_name = service.removeprefix("notify.")
            if critical:
                self.call_service(
                    f"notify/{service_name}", title=title, message=message, data=CRITICAL_PUSH_DATA
                )
            else:
                self.call_service(f"notify/{service_name}", title=title, message=message)

    def _get_name(self, entity):
        """Return the friendly name of an entity including its area, if assigned."""
        name = self.get_state(entity, attribute="friendly_name") or entity
        area = self._get_area(entity)
        if area:
            return f"{name} ({area})"
        return name

    def _get_area(self, entity):
        """Return the area name of an entity from Home Assistant, None if not assigned."""
        area = self.render_template(f"{{{{ area_name('{entity}') }}}}")
        if not area or area == "None":
            return None
        return area

    def _get_time(self):
        """Return the current time as HH:MM string."""
        return self.datetime().strftime("%H:%M")


class WaterAlarm(AlarmNotifier):
    """Notification on water leakage detectors."""

    ALARM_TYPE = "Water alarm"


class SmokeAlarm(AlarmNotifier):
    """Notification on smoke detectors."""

    ALARM_TYPE = "Smoke alarm"
