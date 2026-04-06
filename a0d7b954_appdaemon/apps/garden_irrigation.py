"""
Garden Irrigation Controller (with Interlocking & App-Protection)

Description:
Controls 2 valves with mutual exclusion (only one valve at a time).
Supports auto-schedules, manual toggle via Shelly Pro 2 inputs, and 
safety-timers for manual activation via Home Assistant App.

Interlock Logic:
When Valve A starts, Valve B is explicitly turned off and its timers cancelled.
"""

import appdaemon.plugins.hass.hassapi as hass

class GardenIrrigation(hass.Hass):
    """Garden Irrigation Controller with Interlock and App-Protection
    """
    def initialize(self):
        """Initialize function for appdaemon task.
        """
        self.handles = {"v1": None, "v2": None}
        self.daily_v1 = None
        self.daily_v2 = None

        self.valves = {
            "v1": self.args.get("valve_1"),
            "v2": self.args.get("valve_2")
        }
        self.inputs = {
            "v1": self.args.get("input_1"),
            "v2": self.args.get("input_2")
        }
        self.mode = self.args.get("mode_entity")
        self.duration = self.args.get("duration_entity")
        self.starts = {
            "v1": self.args.get("start_1_entity"),
            "v2": self.args.get("start_2_entity")
        }

        # 1. Listen for Manual Hardware Triggers (Shelly Inputs)
        for key, entity in self.inputs.items():
            if entity:
                self.listen_state(self.manual_trigger_callback, entity, valve_key=key)

        # 2. Listen for State Changes of the Valves (App/UI Triggers)
        for key, entity in self.valves.items():
            if entity:
                self.listen_state(self.valve_state_callback, entity, valve_key=key)

        # 3. Listen for Changes in Start Times
        self.listen_state(self.reschedule_callback, self.starts["v1"])
        self.listen_state(self.reschedule_callback, self.starts["v2"])

        self.reschedule_callback(None, None, None, None, None)
        self.log("Garden Irrigation with Interlock and App-Protection initialized.")

    def reschedule_callback(self, _entity, _attribute, _old, _new, _kwargs):
        """Reschedule the valves based on the new start times
        """
        self.log("Rescheduling valves based on new start times.")
        if self.daily_v1: 
            self.cancel_timer(self.daily_v1)
        if self.daily_v2: 
            self.cancel_timer(self.daily_v2)

        t1 = self.get_state(self.starts["v1"])
        t2 = self.get_state(self.starts["v2"])

        if t1: 
            self.daily_v1 = self.run_daily(self.auto_start_callback, t1, valve_key="v1")
        if t2: 
            self.daily_v2 = self.run_daily(self.auto_start_callback, t2, valve_key="v2")
        self.log(f"Schedule: V1@{t1}, V2@{t2}")

    def auto_start_callback(self, kwargs):
        """Callback for automatic start based on schedule
        """
        self.log(f"Auto start triggered for {kwargs['valve_key']}")
        if self.get_state(self.mode) == "Automatic":
            self.start_irrigation(kwargs['valve_key'])

    def manual_trigger_callback(self, entity, _attribute, old, new, kwargs):
        """Callback for manual toggle via physical Shelly input
        """
        v_key = kwargs['valve_key']
        if old == "off" and new == "on":
            self.log(f"Manual HW trigger (pos edge) for {v_key}")
            self.start_irrigation(v_key)
        elif old == "on" and new == "off":
            self.log(f"Manual HW trigger (neg edge) for {v_key}")
            self.stop_irrigation(v_key)

    def valve_state_callback(self, entity, _attribute, old, new, kwargs):
        """Callback to detect external activation (App/Web UI)
        """
        v_key = kwargs['valve_key']
        # If valve turns ON and NO handle exists, it was started externally
        if old == "off" and new == "on":
            if self.handles[v_key] is None:
                self.log(f"External trigger (App/UI) detected for {v_key}. Applying duration.")
                self.start_irrigation(v_key)

    def start_irrigation(self, valve_key):
        """Starts a valve and stops the other one (Interlock)
        """
        self.log(f"Starting irrigation for {valve_key}")
        other_key = "v2" if valve_key == "v1" else "v1"

        # 1. Interlock: Stop the other valve first
        if self.get_state(self.valves[other_key]) == "on":
            self.log(f"Interlock: Stopping {other_key} because {valve_key} starts.")
            self.stop_irrigation(other_key)

        # 2. Get duration
        duration_state = self.get_state(self.duration)
        duration = float(duration_state) if duration_state else 0

        if duration <= 0:
            self.log(f"Duration for {valve_key} is 0, skipping.")
            return

        # 3. Start this valve (or keep it on if already on)
        self.turn_on(self.valves[valve_key])
        self.log(f"Valve {valve_key} ON for {duration} min")

        # 4. Timer management
        if self.handles[valve_key]:
            self.cancel_timer(self.handles[valve_key])

        self.handles[valve_key] = self.run_in(
            self.stop_irrigation_callback, 
            duration * 60, 
            valve_key=valve_key
        )

    def stop_irrigation_callback(self, kwargs):
        """Callback for stop irrigation after duration
        """
        self.log(f"Stopping irrigation for {kwargs['valve_key']}")
        self.stop_irrigation(kwargs['valve_key'])

    def stop_irrigation(self, valve_key):
        """Cleanup and turn off
        """
        self.log(f"Stopping irrigation for {valve_key}")
        if self.handles[valve_key]:
            self.cancel_timer(self.handles[valve_key])
            self.handles[valve_key] = None

        self.turn_off(self.valves[valve_key])
        self.log(f"Valve {valve_key} OFF.")
