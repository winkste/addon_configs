"""
Garden Irrigation Controller with Weather Intelligence (Sequential Version)

Description:
Extends the base Garden Irrigation controller with weather awareness:
- Controls 2 valves with mutual exclusion (Interlock).
- Sequential logic: V2 starts automatically after V1 finishes (only in Auto-Mode).
- Weather protection: Only auto-starts if no rain detected in last 6 hours.
- Manual overrides always work regardless of weather.
- Rain event tracking: Sets a 6-hour blockout timer when rain is detected.

Requires:
- A weather entity (e.g., weather.forecast) or a rain sensor (binary_sensor or sensor with rain data)
- All entities from base GardenIrrigation app
"""

import appdaemon.plugins.hass.hassapi as hass
from datetime import datetime, timedelta

class GardenIrrigationWeather(hass.Hass):
    """Garden Irrigation Controller with Weather Intelligence
    """
    def initialize(self):
        """Initialize function for AppDaemon task.
        """
        self.handles = {"v1": None, "v2": None}
        self.remaining_seconds = {"v1": 0, "v2": 0}
        self.daily_start1 = None
        self.daily_start2 = None
        self.sequence_active = False

        # Weather/Rain tracking
        self.rain_blockout_timer = None
        self.rain_blocked_until = None
        self.last_rain_time = None

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
        self.duration = self.args.get("duration_entity")
        
        # Start times for the whole sequence
        self.starts = {
            "s1": self.args.get("start_sequence_1"),
            "s2": self.args.get("start_sequence_2")
        }

        # Weather configuration
        self.weather_entity = self.args.get("weather_entity")  # e.g. weather.forecast
        self.rain_sensor = self.args.get("rain_sensor")  # optional rain binary sensor
        self.rain_blockout_hours = self.args.get("rain_blockout_hours", 6)
        self.rainy_states = self.args.get("rainy_states", ["rainy", "pouring", "snowy"])
        
        # Hydration balance model configuration
        self.water_consumption_per_day = float(self.args.get("water_consumption_per_day", 5.0))  # mm/day
        self.water_per_minute = float(self.args.get("water_per_minute", 1.0))  # mm/min
        self.hydrated_level_entity = self.args.get("hydrated_level_entity")  # HA helper number entity
        self.hydrated_level_max = float(self.args.get("hydrated_level_max", 100.0))  # upper bound (mm)
        self.hydrated_level_min = float(self.args.get("hydrated_level_min", -50.0))  # lower bound (mm)
        
        # Initialize hydrated_level from helper entity or start at 0
        self.hydrated_level = 0.0
        if self.hydrated_level_entity:
            try:
                stored = self.get_state(self.hydrated_level_entity)
                if stored and stored not in ["unknown", "unavailable"]:
                    self.hydrated_level = float(stored)
                    self.log(f"Initialized hydrated_level from {self.hydrated_level_entity}: {self.hydrated_level}mm")
            except (ValueError, TypeError):
                self.log(f"WARNING: Could not parse hydrated_level from {self.hydrated_level_entity}", level="WARNING")
        
        # Track if daily hydration check has been done
        self.daily_check_done = False

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

        # 4. Listen for Weather Changes (rain detection)
        if self.weather_entity:
            self.listen_state(self.weather_callback, self.weather_entity)
            # Check initial weather state on startup
            self.run_in(self.check_initial_weather, 2)
        if self.rain_sensor:
            self.listen_state(self.rain_sensor_callback, self.rain_sensor)
        
        # Periodic weather check every 30 minutes to catch edge cases
        if self.weather_entity or self.rain_sensor:
            self.run_every(self.periodic_weather_check, "now", 30 * 60)

        # Daily reset of hydration check flag at midnight
        self.run_daily(self.reset_daily_check, "23:30:00")

        # Initial schedule setup
        self.reschedule_callback(None, None, None, None, None)
        self.log("Weather-aware Sequential Garden Irrigation initialized.")

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

        if t1:
            self.daily_start1 = self.run_daily(self.auto_sequence_start_callback, t1)
        if t2:
            self.daily_start2 = self.run_daily(self.auto_sequence_start_callback, t2)
        self.log(f"Schedule: Start1@{t1}, Start2@{t2}")

    def auto_sequence_start_callback(self, kwargs):
        """Starts the sequence (V1 followed by V2) if mode is Automatic AND weather allows
        """
        if self.get_state(self.mode) != "Automatic":
            self.log("Mode is not Automatic; skipping auto sequence start.")
            return

        if self.is_rain_blocked():
            self.log(f"Rain blockout active until {self.rain_blocked_until}; skipping auto sequence start.")
            return
        
        # Perform daily hydration balance check once per day (at first sequence trigger)
        if not self.daily_check_done:
            self.daily_check_done = True
            try:
                irrigation_allowed, details = self._check_hydration_balance()
            except Exception as e:
                self.log(f"WARNING: Failed to evaluate hydration balance: {e}. Proceeding with caution.", level="WARNING")
                irrigation_allowed = True

            if not irrigation_allowed:
                self.log(f"Auto sequence blocked by hydration balance check: {details}")
                return
        
        self.log("Auto start: V1 starting, V2 will follow (hydration OK).")
        self.start_irrigation("v1", is_auto_sequence=True)


    def _check_hydration_balance(self):
        """Check soil hydration balance for today.
        
        Balance = hydrated_level - water_consumption_per_day + today_forecast
        If balance >= 0: sufficient water (block irrigation)
        If balance < 0: water deficit (allow irrigation)
        
        Returns (True, details) if irrigation allowed (deficit), otherwise (False, details).
        """
        # Fetch today's precipitation forecast
        today_precip = self._get_today_precipitation()
        
        # Calculate today's balance
        balance = self.hydrated_level - self.water_consumption_per_day + today_precip
        
        details = (f"Hydration check: Current={self.hydrated_level:.1f}mm, "
                   f"Consumption=-{self.water_consumption_per_day:.1f}mm, "
                   f"Forecast=+{today_precip:.1f}mm, "
                   f"Balance={balance:.1f}mm")
        
        # Log the balance calculation
        self.log(details)
        
        # If balance is still negative, we need irrigation
        allow_irrigation = (balance < 0.0)
        
        if allow_irrigation:
            self.log(f"Hydration deficit detected ({balance:.1f}mm). Irrigation allowed.")
        else:
            self.log(f"Sufficient hydration ({balance:.1f}mm). Irrigation blocked.")
        
        return allow_irrigation, details

    def _get_today_precipitation(self):
        """Fetch today's precipitation forecast.
        
        Returns the precipitation value (mm) for today, or 0.0 if unavailable.
        """
        forecast_list = []
        try:
            response = self.call_service(
                "weather",
                "get_forecasts",
                entity_id=self.weather_entity,
                type="daily",
                return_response=True
            )
        except Exception:
            response = None

        if isinstance(response, dict):
            try:
                if response.get("success") is False or response.get("error"):
                    response = None
                else:
                    result = response.get("result", {})
                    resp = result.get("response", {}) if isinstance(result, dict) else {}
                    weather_data = resp.get(self.weather_entity, {}) if isinstance(resp, dict) else {}
                    forecast_list = weather_data.get("forecast", []) if isinstance(weather_data, dict) else []
            except Exception:
                forecast_list = []

        # Fallback to entity attributes
        if not forecast_list:
            attrs = self.get_state(self.weather_entity, attribute="all")
            if isinstance(attrs, dict) and "attributes" in attrs:
                forecast_list = attrs["attributes"].get("forecast", [])

        # Extract today's precipitation (first entry)
        if forecast_list:
            today = forecast_list[0]
            precip = float(today.get("precipitation", 0.0) or 0.0)
            return precip
        
        return 0.0

    def is_rain_blocked(self):
        """Check if irrigation is currently blocked due to recent rain
        """
        if self.rain_blocked_until is None:
            return False
        if datetime.now() < self.rain_blocked_until:
            return True
        else:
            self.rain_blocked_until = None
            self.log("Rain blockout expired.")
            return False

    def weather_callback(self, entity, _attribute, old, new, kwargs):
        """Monitor weather entity for rain state
        """
        if new is None:
            self.log(f"Weather state is None; ignoring.", level="WARNING")
            return
        
        self.log(f"Weather state changed: {old} -> {new}")
        if new in self.rainy_states:
            self.log(f"Rain detected via weather entity ({new}). Setting blockout.")
            self.set_rain_blockout()

    def check_initial_weather(self, kwargs):
        """Check weather state on app startup
        """
        if not self.weather_entity:
            return
        
        state = self.get_state(self.weather_entity)
        self.log(f"Initial weather check: {state}")
        if state in self.rainy_states:
            self.log("Rain detected on startup. Setting blockout.")
            self.set_rain_blockout()

    def periodic_weather_check(self, kwargs):
        """Periodic check every 30 minutes to ensure blockout is maintained if raining
        """
        if self.weather_entity:
            state = self.get_state(self.weather_entity)
            if state and state in self.rainy_states:
                # If it's still raining, extend the blockout
                if not self.is_rain_blocked():
                    self.log(f"Periodic check: Rain still active ({state}). Re-extending blockout.")
                    self.set_rain_blockout()
        
        if self.rain_sensor:
            state = self.get_state(self.rain_sensor)
            is_raining = (state == "on") or (isinstance(state, (int, float)) and float(state) > 0)
            if is_raining and not self.is_rain_blocked():
                self.log(f"Periodic check: Rain sensor still active. Re-extending blockout.")
                self.set_rain_blockout()

    def reset_daily_check(self, kwargs):
        """Reset the daily hydration check flag at midnight
        """
        self.daily_check_done = False
        self.log("Daily hydration check flag reset for new day")

    def rain_sensor_callback(self, entity, _attribute, old, new, kwargs):
        """Monitor rain sensor (binary or numeric) for precipitation
        """
        self.log(f"Rain sensor changed: {old} -> {new}")
        # Treat as rain if: binary "on", or numeric > 0
        is_raining = (new == "on") or (isinstance(new, (int, float)) and float(new) > 0)
        if is_raining:
            self.log("Rain detected via sensor. Setting blockout.")
            self.set_rain_blockout()

    def set_rain_blockout(self):
        """Set a blockout timer for the configured rain blockout period
        """
        self.last_rain_time = datetime.now()
        self.rain_blocked_until = datetime.now() + timedelta(hours=self.rain_blockout_hours)
        
        # Cancel existing blockout timer if any
        if self.rain_blockout_timer:
            self.cancel_timer(self.rain_blockout_timer)
        
        # Schedule a callback to clear the blockout
        self.rain_blockout_timer = self.run_in(
            self.clear_rain_blockout_callback,
            self.rain_blockout_hours * 3600
        )
        self.log(f"Rain blockout set for {self.rain_blockout_hours} hours (until {self.rain_blocked_until.strftime('%H:%M:%S')})")

    def clear_rain_blockout_callback(self, kwargs):
        """Clear the rain blockout after the timeout
        """
        self.rain_blocked_until = None
        self.rain_blockout_timer = None
        self.log("Rain blockout cleared.")

    def manual_trigger_callback(self, entity, _attribute, old, new, kwargs):
        """Manual HW toggle: Always works, regardless of weather
        """
        v_key = kwargs['valve_key']
        if old == "off" and new == "on":
            self.log(f"Manual trigger on {v_key} (weather blocked: {self.is_rain_blocked()})")
            self.start_irrigation(v_key, is_auto_sequence=False)
        elif old == "on" and new == "off":
            self.sequence_active = False
            self.stop_irrigation(v_key)

    def valve_state_callback(self, entity, _attribute, old, new, kwargs):
        """App/UI trigger: Always works, regardless of weather
        """
        v_key = kwargs['valve_key']
        if old == "off" and new == "on":
            if self.handles[v_key] is None:
                self.log(f"External trigger {v_key} (weather blocked: {self.is_rain_blocked()})")
                self.start_irrigation(v_key, is_auto_sequence=False)
        elif old == "on" and new == "off":
            self.log(f"App/UI turned off {v_key}. Cancelling sequence state.")
            self.sequence_active = False
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

        if is_auto_sequence:
            self.sequence_active = True
        else:
            self.sequence_active = False

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

        # Sequence logic: Proceed only if all conditions are met
        if (is_auto_sequence and self.sequence_active and valve_key == "v1" 
            and self.get_state(self.mode) == "Automatic" and not self.is_rain_blocked()):
            self.log("V1 finished naturally. Now starting V2 in sequence.")
            self.start_irrigation("v2", is_auto_sequence=True)

        elif is_auto_sequence and valve_key == "v2":
            self.log("Auto-sequence finished.")
            self.sequence_active = False
            self.daily_check_done = False

            # Update hydrated_level ONLY HERE when the entire sequence is fully done
            duration_state = self.get_state(self.duration)
            duration = float(duration_state) if duration_state else 0
            if duration > 0:
                water_added = duration * self.water_per_minute
                self.hydrated_level += water_added

                if self.hydrated_level > self.hydrated_level_max:
                    self.hydrated_level = self.hydrated_level_max
                elif self.hydrated_level < self.hydrated_level_min:
                    self.hydrated_level = self.hydrated_level_min

                if self.hydrated_level_entity:
                    self.set_value(self.hydrated_level_entity, round(self.hydrated_level, 1))

                self.log(f"Updated hydrated_level after complete sequence finish: +{water_added:.1f}mm -> {self.hydrated_level:.1f}mm")

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
