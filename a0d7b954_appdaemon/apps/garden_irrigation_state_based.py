"""
State-Based Garden Irrigation Controller

Description:
A state-driven sequential irrigation system that manages a dynamic soil 
hydration budget (hydrated_level). 
- Polls weather forecasts every 30 minutes to populate a temporary forecast tracking helper.
- Executes sequence starts conditionally: runs if (hydrated_level + temp_forecast) < 0.
- Sequence runs strictly sequentially: Valve 1 followed immediately by Valve 2.
- Commits actual water volume to the real hydrated_level only on successful completion.
- Re-evaluates and shifts balances deterministically at midnight (00:00).
- Fully safe against restarts: instantly shuts down hanging valves on initialization.
"""

import appdaemon.plugins.hass.hassapi as hass
from datetime import datetime, time

class GardenIrrigationStateBased(hass.Hass):
    """State-driven garden irrigation controller with dynamic soil budget tracking.
    """
    def initialize(self):
        """Initializes state mappings, schedulers, and registers execution callbacks.
        """
        # Internal runtime state management
        self.handles = {"v1": None, "v2": None}
        self.safety_handles = {"v1": None, "v2": None}
        self.remaining_seconds = {"v1": 0, "v2": 0}
        self.daily_start1 = None
        self.daily_start2 = None
        self.sequence_active = False

        # Load environment variables and entity targets from arguments
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

        # Core control configuration hooks
        self.mode = self.args.get("mode_entity")
        self.duration = self.args.get("duration_entity")
        self.weather_entity = self.args.get("weather_entity")

        # Dynamic state model entities (HA Helpers)
        self.hydrated_level_entity = self.args.get("hydrated_level_entity")
        self.temp_forecast_entity = self.args.get("temp_forecast_entity")

        # Scheduling targets
        self.starts = {
            "s1": self.args.get("start_sequence_1"),
            "s2": self.args.get("start_sequence_2")
        }

        # Value model parameters
        self.water_consumption_per_day = float(self.args.get("water_consumption_per_day", 5.0))
        self.water_per_minute = float(self.args.get("water_per_minute", 0.55))
        self.hydrated_level_max = float(self.args.get("hydrated_level_max", 30.0))
        self.hydrated_level_min = float(self.args.get("hydrated_level_min", -50.0))

        # Runtime counter daemon loop (updates remaining timers every 60 seconds)
        self.run_every(self.update_countdown, "now", 60)

        # Register event handlers for local interface controls (Shelly Inputs)
        for key, entity in self.inputs.items():
            if entity:
                self.listen_state(self.manual_trigger_callback, entity, valve_key=key)

        # Register event handlers for logical software entity switches (HA Dashboard toggles)
        for key, entity in self.valves.items():
            if entity:
                self.listen_state(self.valve_state_callback, entity, valve_key=key)

        # Monitor modifications to scheduling timers dynamically
        if self.starts.get("s1"):
            self.listen_state(self.reschedule_callback, self.starts["s1"])
        if self.starts.get("s2"):
            self.listen_state(self.reschedule_callback, self.starts["s2"])

        # Periodic asynchronous weather query thread execution (runs every 30 minutes)
        if self.weather_entity:
            self.run_every(self.update_temporary_forecast_callback, "now", 30 * 60)

        # Schedule deterministic daily state shift processing exactly at midnight
        self.run_daily(self.process_midnight_balance_shift, time(0, 0, 0))

        # CRITICAL SAFETY CHECK ON BOOT / RESTART:
        # If AppDaemon reboots while a valve is physisch open, force it close immediately
        # to prevent infinite flooding, since all memory timers were wiped.
        self.log("Performing startup valve safety check...")
        for key, entity in self.valves.items():
            if entity:
                current_hardware_state = self.get_state(entity)
                if current_hardware_state == "on":
                    self.log(f"WARNING: Valve {key} ({entity}) was found ON during AppDaemon startup! Forcing emergency shutdown.", level="WARNING")
                    self.stop_irrigation(key)

        # Execute dynamic schedule pipeline calculations
        self.reschedule_callback(None, None, None, None, None)
        self.log("State-Based Garden Irrigation Controller successfully initialized.")

    def update_countdown(self, kwargs):
        """Decrements current tracking runtime counters and sets dashboard display sensors.
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
        """Re-calculates daily operational timelines on scheduler modification configurations.
        """
        self.log("Rescheduling automated execution pipelines.")
        if self.daily_start1:
            self.cancel_timer(self.daily_start1)
        if self.daily_start2:
            self.cancel_timer(self.daily_start2)

        t1 = self.get_state(self.starts["s1"])
        t2 = self.get_state(self.starts["s2"])

        if t1:
            self.daily_start1 = self.run_daily(self.auto_sequence_start_callback, t1)
        if t2:
            self.daily_start2 = self.run_daily(self.auto_sequence_start_callback, t2)
        self.log(f"Configured Schedule Tracks: Start1@{t1}, Start2@{t2}")

    def update_temporary_forecast_callback(self, kwargs):
        """Asynchronously updates the temporary precipitation forecast sensor tracking value.
        """
        if not self.weather_entity or not self.temp_forecast_entity:
            return

        forecast_list = []
        try:
            response = self.call_service(
                "weather/get_forecasts",
                entity_id=self.weather_entity,
                type="daily",
                return_response=True
            )
        except Exception as e:
            self.log(f"Weather service call execution failure: {e}", level="WARNING")
            response = None

        if isinstance(response, dict) and 'result' in response:
            result = response['result']
            if isinstance(result, dict) and 'response' in result:
                weather_data = result['response'].get(self.weather_entity, {})
                forecast_list = weather_data.get('forecast', [])

        # Fallback to checking static attributes directly if service structure failed
        if not forecast_list:
            attrs = self.get_state(self.weather_entity, attribute="all")
            if isinstance(attrs, dict) and "attributes" in attrs:
                forecast_list = attrs["attributes"].get("forecast", [])

        if forecast_list:
            today_data = forecast_list[0]
            precip_today = float(today_data.get("precipitation", 0.0) or 0.0)

            # Sync value to Home Assistant interface helper
            self.set_value(self.temp_forecast_entity, round(precip_today, 1))
            self.log(f"Polled weather update: Temporary today precipitation forecast is {precip_today}mm")
        else:
            self.log("Unable to extract valid forecast structure payload.", level="WARNING")

    def auto_sequence_start_callback(self, kwargs):
        """Evaluates state metrics at scheduled triggers and executes sequence if state requires water.
        """
        if self.get_state(self.mode) != "Automatic":
            self.log("Operational system configuration mode is not Automatic; aborting sequence start.")
            return

        # Fetch latest state parameters directly from the UI interface models
        try:
            hydrated_level = float(self.get_state(self.hydrated_level_entity) or 0.0)
            temp_forecast = float(self.get_state(self.temp_forecast_entity) or 0.0)
        except (ValueError, TypeError) as e:
            self.log(f"CRITICAL: System state calculation failure, tracking data corrupted: {e}", level="ERROR")
            return

        # State decision equation: Is the total predictive hydration balance below 0.0?
        predictive_balance = hydrated_level + temp_forecast
        self.log(f"Evaluating automated irrigation: Current Budget={hydrated_level:.1f}mm, Today Temp Forecast=+{temp_forecast:.1f}mm. Target Balance={predictive_balance:.1f}mm")

        if predictive_balance >= 0.0:
            self.log(f"Automated sequence bypassed: Combined balance ({predictive_balance:.1f}mm) indicates sufficient soil moisture.")
            return

        self.log(f"Target deficit confirmed ({predictive_balance:.1f}mm). Initializing irrigation cycle sequence.")
        self.start_irrigation("v1", is_auto_sequence=True)

    def process_midnight_balance_shift(self, kwargs):
        """Processes state transition matrix updates precisely at midnight (00:00).
        Equation: New Level = Current Level - Consumption + Realized Today Forecast
        """
        self.log("Midnight boundary reached. Shifting state balance structures.")
        try:
            current_level = float(self.get_state(self.hydrated_level_entity) or 0.0)
            realized_rain = float(self.get_state(self.temp_forecast_entity) or 0.0)
        except (ValueError, TypeError) as e:
            self.log(f"State transition engine halted due to calculation exception: {e}", level="ERROR")
            return

        # Core arithmetic model shift calculation
        new_level = current_level - self.water_consumption_per_day + realized_rain

        # Enforce strict boundary rules constraints
        if new_level > self.hydrated_level_max:
            new_level = self.hydrated_level_max
        elif new_level < self.hydrated_level_min:
            new_level = self.hydrated_level_min

        # Commit shift changes to external persistent state models
        if self.hydrated_level_entity:
            self.set_value(self.hydrated_level_entity, round(new_level, 1))

        # Flash temporary variable storage arrays back to neutral zero state tracking
        if self.temp_forecast_entity:
            self.set_value(self.temp_forecast_entity, 0.0)

        self.log(f"State shift complete: Budget={current_level:.1f}mm, Consumption=-{self.water_consumption_per_day:.1f}mm, Rain=+{realized_rain:.1f}mm -> New Budget Target={new_level:.1f}mm")

    def manual_trigger_callback(self, entity, _attribute, old, new, kwargs):
        """Manual HW interface callback toggles. Bypasses predictive state checking.
        """
        v_key = kwargs['valve_key']
        if old == "off" and new == "on":
            self.log(f"Hardware input hardware interrupt switch detected on {v_key}. Initializing forced manual run.")
            self.start_irrigation(v_key, is_auto_sequence=False)
        elif old == "on" and new == "off":
            self.sequence_active = False
            self.stop_irrigation(v_key)

    def valve_state_callback(self, entity, _attribute, old, new, kwargs):
        """Software interface entity state modification tracker.
        """
        v_key = kwargs['valve_key']
        if old == "off" and new == "on":
            if self.handles[v_key] is None:
                self.log(f"Software interface entity ignition toggle registered on {v_key}.")
                self.start_irrigation(v_key, is_auto_sequence=False)
        elif old == "on" and new == "off":
            self.log(f"Software manual interface override event triggered 'off' for {v_key}. Terminating sequence chains.")
            self.sequence_active = False
            self.stop_irrigation(v_key)

    def start_irrigation(self, valve_key, is_auto_sequence=False):
        """Fires valve actuator execution pins. Enforces runtime hardware interlocks.
        """
        other_key = "v2" if valve_key == "v1" else "v1"

        # Interlock: Terminate competing hardware relay operations immediately
        if self.valves.get(other_key) and self.get_state(self.valves[other_key]) == "on":
            self.stop_irrigation(other_key)

        duration_state = self.get_state(self.duration)
        duration = float(duration_state) if duration_state else 0

        if duration <= 0:
            self.log("Irrigation initialization canceled: target duration input scale set to 0.", level="WARNING")
            return

        if not self.valves.get(valve_key):
            self.log(f"Hardware link missing parameter definition mapping for {valve_key}.", level="ERROR")
            return

        self.sequence_active = is_auto_sequence
        self.turn_on(self.valves[valve_key])

        # Clean runtime operational registers
        if self.handles[valve_key] and self.timer_running(self.handles[valve_key]):
            self.cancel_timer(self.handles[valve_key])
        if self.safety_handles.get(valve_key) and self.timer_running(self.safety_handles[valve_key]):
            self.cancel_timer(self.safety_handles[valve_key])

        self.remaining_seconds[valve_key] = int(duration * 60)

        # Set hardware tracking watchdog callbacks
        self.handles[valve_key] = self.run_in(
            self.stop_irrigation_callback,
            int(duration * 60),
            valve_key=valve_key,
            is_auto_sequence=is_auto_sequence
        )

        # Independent hardware physical failure escape timer line
        self.safety_handles[valve_key] = self.run_in(
            self.safety_emergency_shutdown,
            int((duration + 5) * 60),
            valve_key=valve_key
        )

        self.log(f"Valve channel {valve_key} activated. Sequence-Mode={is_auto_sequence}. Watchdog assigned.")

    def stop_irrigation_callback(self, kwargs):
        """Processes automated step state progressions on normal runtime completion intervals.
        """
        valve_key = kwargs['valve_key']
        is_auto_sequence = kwargs.get('is_auto_sequence', False)

        self.stop_irrigation(valve_key)

        # Sequence Automation Progression Matrix Routing
        if is_auto_sequence and self.sequence_active and valve_key == "v1" and self.get_state(self.mode) == "Automatic":
            self.log("Valve channel v1 cycle task finished. Stepping automation queue directly to v2.")
            self.start_irrigation("v2", is_auto_sequence=True)

        elif is_auto_sequence and valve_key == "v2":
            self.log("Automated sequence pipeline run fully completed with success. Calculating budget injection values.")
            self.sequence_active = False

            # Update real persistent state models ONLY after complete clean run execution
            duration_state = self.get_state(self.duration)
            duration = float(duration_state) if duration_state else 0
            if duration > 0:
                water_added = duration * self.water_per_minute

                try:
                    current_budget = float(self.get_state(self.hydrated_level_entity) or 0.0)
                    new_budget = current_budget + water_added

                    if new_budget > self.hydrated_level_max:
                        new_budget = self.hydrated_level_max
                    elif new_budget < self.hydrated_level_min:
                        new_budget = self.hydrated_level_min

                    if self.hydrated_level_entity:
                        self.set_value(self.hydrated_level_entity, round(new_budget, 1))
                    self.log(f"Hydration account updated successfully: Budget={current_budget:.1f}mm, Deposited=+{water_added:.1f}mm -> Final Budget={new_budget:.1f}mm")
                except (ValueError, TypeError) as e:
                    self.log(f"Failed to deposit calculated run volume to state helper entity model: {e}", level="ERROR")

    def safety_emergency_shutdown(self, kwargs):
        """Hard emergency line handler. Triggers only if hardware fails to yield execution state on time.
        """
        valve_key = kwargs['valve_key']
        if self.valves.get(valve_key) and self.get_state(self.valves[valve_key]) == "on":
            self.log(f"CRITICAL DESYNC ENCOUNTERED: Hardware interface {valve_key} bypassed scheduler deadlines! Executing defensive force down.", level="WARNING")
            self.sequence_active = False
            self.stop_irrigation(valve_key)

    def stop_irrigation(self, valve_key):
        """Termitnates hardware power links, clears open tracking loops, and zeroes active sensors.
        """
        if self.handles[valve_key] and self.timer_running(self.handles[valve_key]):
            self.cancel_timer(self.handles[valve_key])
        self.handles[valve_key] = None

        if self.safety_handles.get(valve_key) and self.timer_running(self.safety_handles[valve_key]):
            self.cancel_timer(self.safety_handles[valve_key])
        self.safety_handles[valve_key] = None

        self.remaining_seconds[valve_key] = 0

        entity = self.resttime_entities[valve_key]
        if entity:
            self.set_value(entity, 0)

        if self.valves.get(valve_key):
            self.turn_off(self.valves[valve_key])
        self.log(f"Valve channel {valve_key} forced to OFF state line.")