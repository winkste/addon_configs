"""
Garden Irrigation Controller (Sequential Version)

Description:
Controls 2 valves with mutual exclusion (Interlock).
Features:
- Scheduled auto-start (2 start times for the WHOLE sequence V1 -> V2).
- Sequential logic: V2 starts automatically after V1 finishes (only in Auto-Mode).
- Manual toggle via Shelly hardware inputs (standalone, no sequence).
- App-Protection: Auto-off timer if started via HA App/UI (standalone).
- Countdown: Real-time remaining time updates in HA sensors.
"""

import appdaemon.plugins.hass.hassapi as hass

class GardenIrrigation(hass.Hass):
    """Garden Irrigation Controller with Sequential Auto-Mode
    """
    def initialize(self):
        """Initialize function for AppDaemon task.
        """
        self.handles = {"v1": None, "v2": None}
        self.remaining_seconds = {"v1": 0, "v2": 0}
        self.daily_start1 = None
        self.daily_start2 = None

        # Load entities from arguments
        self.valves = {
            "v1": self.args.get("valve_1"),
            "v2": self.args.get("valve_2")
        }
        self.inputs = {
            "v1": self.args.get("input_1"),
            "v2": self.args.get("input_2")
        }
        self.resttime_entities = {
            "v1": self.args.get("sensor_remaining_1"),
            "v2": self.args.get("sensor_remaining_2")
        }

        self.mode = self.args.get("mode_entity")
        self.duration = self.args.get("duration_entity") # Currently combined duration for all sequences
        
        # Start times for the whole sequence
        self.starts = {
            "s1": self.args.get("start_sequence_1"),
            "s2": self.args.get("start_sequence_2")
        }

        # Timer for Countdown-Update (every 60 seconds)
        self.run_every(self.update_countdown, "now", 60)

        # 1. Listen for Manual Hardware Triggers (Shelly Inputs)
        for key, entity in self.inputs.items():
            if entity:
                self.listen_state(self.manual_trigger_callback, entity, valve_key=key)

        # 2. Listen for State Changes of the Valves (App/UI Triggers)
        for key, entity in self.valves.items():
            if entity:
                self.listen_state(self.valve_state_callback, entity, valve_key=key)

        # 3. Listen for Changes in Sequence Start Times
        if self.starts.get("s1"):
            self.listen_state(self.reschedule_callback, self.starts["s1"])
        if self.starts.get("s2"):
            self.listen_state(self.reschedule_callback, self.starts["s2"])

        # Initial schedule setup
        self.reschedule_callback(None, None, None, None, None)
        self.log("Sequential Garden Irrigation initialized.")

    def update_countdown(self, kwargs):
        """Decrements internal counter and updates HA sensors
        """
        for key in ["v1", "v2"]:
            if self.remaining_seconds[key] > 0:
                self.remaining_seconds[key] -= 60
                if self.remaining_seconds[key] < 0:
                    self.remaining_seconds[key] = 0

            entity = self.resttime_entities[key]
            if entity:
                minutes_left = int((self.remaining_seconds[key] + 59) / 60) if self.remaining_seconds[key] > 0 else 0
                self.set_value(entity, minutes_left)

    def reschedule_callback(self, _entity, _attribute, _old, _new, _kwargs):
        """Reschedule the sequence start times
        """
        self.log("Rescheduling sequence starts.")
        if self.daily_start1:
            self.cancel_timer(self.daily_start1)
        if self.daily_start2:
            self.cancel_timer(self.daily_start2)

        t1 = self.get_state(self.starts["s1"])
        t2 = self.get_state(self.starts["s2"])

        # Both timers always start the sequence with Valve 1
        if t1:
            self.daily_start1 = self.run_daily(self.auto_sequence_start_callback, t1)
        if t2:
            self.daily_start2 = self.run_daily(self.auto_sequence_start_callback, t2)
        self.log(f"Schedule: Start1@{t1}, Start2@{t2}")

    def auto_sequence_start_callback(self, kwargs):
        """Starts the sequence (V1 followed by V2) if mode is set to Automatic
        """
        if self.get_state(self.mode) == "Automatic":
            self.log("Auto start: V1 starting, V2 will follow.")
            self.start_irrigation("v1", is_auto_sequence=True)

    def manual_trigger_callback(self, entity, _attribute, old, new, kwargs):
        """Manual HW toggle: No sequence, standalone valve operation
        """
        v_key = kwargs['valve_key']
        if old == "off" and new == "on":
            self.start_irrigation(v_key, is_auto_sequence=False)
        elif old == "on" and new == "off":
            self.stop_irrigation(v_key)

    def valve_state_callback(self, entity, _attribute, old, new, kwargs):
        """App/UI trigger: No sequence, standalone valve operation
        """
        v_key = kwargs['valve_key']
        if old == "off" and new == "on":
            if self.handles[v_key] is None:
                self.log(f"External trigger {v_key}. Standalone mode without sequence.")
                self.start_irrigation(v_key, is_auto_sequence=False)
        elif old == "on" and new == "off":
            # App/UI turned off the valve; stop any running timer
            self.log(f"App/UI turned off {v_key}.")
            self.stop_irrigation(v_key)

    def start_irrigation(self, valve_key, is_auto_sequence=False):
        """Starts a valve. is_auto_sequence determines if the next valve should follow.
        """
        other_key = "v2" if valve_key == "v1" else "v1"

        # Interlock: Turn off the other valve
        if self.valves.get(other_key) and self.get_state(self.valves[other_key]) == "on":
            self.stop_irrigation(other_key)

        duration_state = self.get_state(self.duration)
        duration = float(duration_state) if duration_state else 0
        
        if duration <= 0:
            return

        if not self.valves.get(valve_key):
            self.log(f"No valve entity configured for {valve_key}; aborting start.")
            return

        self.turn_on(self.valves[valve_key])

        if self.handles[valve_key]:
            if self.timer_running(self.handles[valve_key]):
                self.cancel_timer(self.handles[valve_key])

        self.remaining_seconds[valve_key] = int(duration * 60)

        # Immediate sensor update
        entity = self.resttime_entities[valve_key]
        if entity:
            self.set_value(entity, int(duration))

        # Set timer for automatic shutoff
        self.handles[valve_key] = self.run_in(
            self.stop_irrigation_callback,
            int(duration * 60),
            valve_key=valve_key,
            is_auto_sequence=is_auto_sequence
        )
        self.log(f"Valve {valve_key} ON. Sequence-Mode: {is_auto_sequence}")

    def stop_irrigation_callback(self, kwargs):
        """Stops the valve and checks if next one in sequence should start
        """
        valve_key = kwargs['valve_key']
        is_auto_sequence = kwargs.get('is_auto_sequence', False)

        self.stop_irrigation(valve_key)

        # Sequence logic: If V1 finished and sequence is active, start V2
        # Only proceed if mode is still Automatic
        if is_auto_sequence and valve_key == "v1" and self.get_state(self.mode) == "Automatic":
            self.log("V1 finished. Now starting V2 in sequence.")
            self.start_irrigation("v2", is_auto_sequence=True)
        elif is_auto_sequence and valve_key == "v2":
            self.log("Auto-sequence finished.")

    def stop_irrigation(self, valve_key):
        """Cleanup timer, turn off hardware and reset sensors
        """
        if self.handles[valve_key]:
            if self.timer_running(self.handles[valve_key]):
                self.cancel_timer(self.handles[valve_key])
            self.handles[valve_key] = None

        self.remaining_seconds[valve_key] = 0

        entity = self.resttime_entities[valve_key]
        if entity:
            self.set_value(entity, 0)

        if self.valves.get(valve_key):
            self.turn_off(self.valves[valve_key])
        else:
            self.log(f"No valve entity configured for {valve_key}; nothing to turn off.")
        self.log(f"Valve {valve_key} OFF.")