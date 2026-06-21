"""
AppDaemon Class: NeoCombinedTemp
Author: AI Collaborator
Version: 1.6

Description:
    A sophisticated lighting controller that manages GU10 RGBW/White groups based on:
    1. Motion: Increases brightness when movement is detected.
    2. Ambient (Sunset): Maintains a base level of light from sunset until a fixed time (22:00).
    3. Temperature: Dynamically maps light color (Kelvin) based on an external temperature sensor.

Functionality:
    - From Sunset to 22:00: Light is in 'Ambient Mode' (dimmed).
    - If Motion is detected: Light brightens. When motion stops, it dims back to Ambient or turns off (if after 22:00).
    - Color Temp: Updated dynamically. Inverted logic: cold weather triggers cozy warm light, warm weather triggers crisp cool light.
    - Matter Stability (Staggered Execution): Automatically expands light groups and spaces out individual commands by 150ms to prevent network packet drops and CHIP Timeout errors.
    - HA Compatibility Fix: Uses modern 'color_temp_kelvin' service parameter instead of deprecated 'kelvin'.
    - Solstice Safety Fix: Prevents stuck ambient states during summer when sunset is calculated after 22:00.

Args:
    sensor (str): Entity ID of the motion sensor (binary_sensor).
    temp_sensor (str): Entity ID of the temperature sensor.
    entity_ctrl (str): Entity ID of the light or light group to control.
    off_delay (int): Seconds to wait after motion ends before turning off/dimming (default: 60).
    sunset_offset (int): Minutes relative to sunset to start ambient mode (default: -15).
    brightness_motion (int): Brightness level (0-255) for motion events (default: 255).
    brightness_ambi (int): Brightness level (0-255) for ambient mode (default: 125).
    cold_kelvin (int): Kelvin value for crisp cool light (default: 6500).
    warm_kelvin (int): Kelvin value for cozy warm light (default: 2700).
    min_temp (float): Low temperature boundary where cozy warm light maximizes (default: 0.0).
    max_temp (float): High temperature boundary where crisp cool light maximizes (default: 25.0).
"""

import appdaemon.plugins.hass.hassapi as hass
import datetime

class NeoCombinedTemp(hass.Hass):
    """Combined controller for motion, ambient, and temperature-based light automation with advanced Matter race-condition protection."""

    def initialize(self):
        """Initialize the App and subscribe to state changes and schedules."""
        # Load configuration arguments
        self.entity_ctrl = self.args.get("entity_ctrl")
        self.motion_sensor = self.args.get("sensor")
        self.temp_sensor = self.args.get("temp_sensor")
        
        self.off_delay = self.args.get("off_delay", 60)
        self.sunset_offset = self.args.get("sunset_offset", -15)
        self.brightness_motion = self.args.get("brightness_motion", 255)
        self.brightness_ambi = self.args.get("brightness_ambi", 25)
        
        self.cold_kelvin = self.args.get("cold_kelvin", 6500)
        self.warm_kelvin = self.args.get("warm_kelvin", 2700)
        self.min_temp = self.args.get("min_temp", 0.0)
        self.max_temp = self.args.get("max_temp", 25.0)

        # Runtime variables
        self.ambi_timer = None
        self.ambi_active = False
        self.manual_override = False
        self._internal_action = False

        # Protection against AppDaemon restarts during evening ambient time
        if self.sun_down() and self.get_now_time() < datetime.time(22, 0, 0):
            self.ambi_active = True

        # Register Motion Callbacks
        if self.motion_sensor:
            self.listen_state(self.motion_on_callback, self.motion_sensor, new="on")
            self.listen_state(self.motion_off_callback, self.motion_sensor, new="off", duration=self.off_delay)
        else:
            self.log("No motion sensor specified. Motion features disabled.")

        # Register Temperature Callback
        if self.temp_sensor:
            self.listen_state(self.temperature_callback, self.temp_sensor)
        else:
            self.log("No temp_sensor specified. Temperature-based color updates disabled.")

        # Register Entity State Callback
        if self.entity_ctrl:
            entities = self._get_entities_to_control()
            for entity in entities:
                self.listen_state(self.entity_state_callback, entity)
            self.run_at_sunset(self.sunset_callback, offset=self.sunset_offset * 60)
        else:
            self.error("No entity_ctrl specified. The app has nothing to control.")

    def motion_on_callback(self, entity, attribute, old, new, kwargs):
        """Handle motion detection."""
        self.log(f"Motion detected on {entity}")
        # Check if sunset rules apply (or bypass if testing via apps.yaml)
        if self.sun_down() or getattr(self, "_bypass_sunset_test", False):
            self.run_in(self._run_apply_state, 0, motion=True)

    def motion_off_callback(self, entity, attribute, old, new, kwargs):
        """Handle motion timeout."""
        self.log(f"Motion cleared on {entity} (timeout reached)")
        self.run_in(self._run_apply_state, 0, motion=False)

    def sunset_callback(self, kwargs):
        """Handle sunset event to start ambient mode, with solstice protection."""
        # SOLSTICE PROTECTION: If sunset triggers AFTER 22:00, DO NOT START ambient mode!
        if self.get_now_time() >= datetime.time(22, 0, 0):
            self.log("Sunset triggered AFTER 22:00. Skipping Ambient Mode activation for tonight.")
            self.ambi_active = False
            return

        self.log("Sunset triggered: Starting Ambient Mode.")
        self.ambi_active = True

        # Apply light state immediately (unless motion is already active)
        if self.get_state(self.motion_sensor) == "off":
            self.apply_light_state(motion=False)

        # Cancel existing timer if it exists
        if self.ambi_timer:
            self.cancel_timer(self.ambi_timer)

        # Schedule the end of ambient mode at 22:00
        self.ambi_timer = self.run_at(self.end_ambient_callback, "22:00:00")

    def end_ambient_callback(self, kwargs):
        """End ambient mode and turn off light if no motion is active."""
        self.log("22:00 reached: Ending Ambient Mode.")
        self.ambi_active = False
        self.ambi_timer = None

        # Turn off light only if no motion is currently detected
        if self.motion_sensor and self.get_state(self.motion_sensor) == "off":
            if self.manual_override:
                self.log("Manual override active; keeping light on after ambient mode ends.")
                return
            self._internal_turn_off()

    def temperature_callback(self, entity, attribute, old, new, kwargs):
        """Handle temperature changes and refresh color if active."""
        self.log(f"Temperature sensor updated: {entity} -> {new}")
        
        # Hard protection: If it is day or no ambient/motion is active, do absolutely nothing!
        if not self.ambi_active and (self.motion_sensor and self.get_state(self.motion_sensor) == "off"):
            return

        if self.ambi_active or (self.motion_sensor and self.get_state(self.motion_sensor) == "on"):
            # Schedule refresh so callbacks remain short
            current_motion = (self.motion_sensor and self.get_state(self.motion_sensor) == "on")
            self.run_in(self._run_apply_state, 0, motion=current_motion)

    def apply_light_state(self, motion=False):
        """Determine the correct brightness and color based on current state."""
        if not self.entity_ctrl:
            return

        kelvin = self.calculate_kelvin()

        if motion:
            # High brightness for motion
            self.log(f"Setting {self.entity_ctrl} to Motion Brightness ({self.brightness_motion}) @ {kelvin}K.")
            self._internal_turn_on(brightness=self.brightness_motion, color_temp_kelvin=kelvin)
        elif self.ambi_active:
            # Return to dimmed ambient brightness
            self.log(f"Setting {self.entity_ctrl} to Ambient Brightness ({self.brightness_ambi}) @ {kelvin}K.")
            self._internal_turn_on(brightness=self.brightness_ambi, color_temp_kelvin=kelvin)
        else:
            if self.manual_override:
                self.log(f"Manual override active; leaving {self.entity_ctrl} on.")
                return
            # Outside of ambient time and no motion: Turn Off
            self.log(f"No motion and Ambient Mode inactive. Turning off {self.entity_ctrl}.")
            self._internal_turn_off()

    def calculate_kelvin(self):
        """Calculate color temperature. Inverted logic: warm when cold, cold when hot."""
        temp_val = None
        if self.temp_sensor:
            state = self.get_state(self.temp_sensor)
            try:
                temp_val = float(state)
            except (ValueError, TypeError):
                self.log(f"Warning: Could not parse temperature '{state}'. Using default.")

        if temp_val is None:
            return self.warm_kelvin  # Default fallback safe cozy light

        # Hard boundaries
        if temp_val <= self.min_temp:
            return self.warm_kelvin  # Freezing cold outside -> Maximum cozy warm light (e.g. 2700K)
        if temp_val >= self.max_temp:
            return self.cold_kelvin  # Boiling hot outside -> Maximum crisp cool light (e.g. 6500K)

        range_temp = self.max_temp - self.min_temp
        if range_temp == 0:
            self.log("min_temp and max_temp are equal; using warm_kelvin fallback.")
            return self.warm_kelvin

        # Inverted linear interpolation logic
        ratio = (temp_val - self.min_temp) / range_temp
        target_kelvin = int(self.warm_kelvin + (self.cold_kelvin - self.warm_kelvin) * ratio)

        self.log(f"Temp: {temp_val}°C -> Color Matrix Output: {target_kelvin}K")
        return target_kelvin

    def _get_entities_to_control(self):
        """Resolve entity_ctrl into individual entities, supporting both lists and single group entities."""
        if isinstance(self.entity_ctrl, list):
            return self.entity_ctrl
            
        members = self.get_state(self.entity_ctrl, attribute="entity_id")
        if isinstance(members, list):
            return members
            
        return [self.entity_ctrl]

    def _internal_turn_on(self, **kwargs):
        """Turn on lights using a staggered/stacked delay loop to prevent Matter command drops."""
        self._internal_action = True
        entities = self._get_entities_to_control()
        
        delay = 0.0
        for entity in entities:
            # Injecting staggered timers to offset the load on the Wi-Fi router
            self.run_in(self._staggered_turn_on_executor, delay, entity=entity, kwargs=kwargs)
            delay += 0.15  # 150 milliseconds gap between each bulb execution
            
        # Clear the internal action shield shortly after the final timer is dispatched
        self.run_in(self._clear_internal_action, delay + 0.5)

    def _staggered_turn_on_executor(self, timer_kwargs):
        """Directly sends the Home Assistant turn_on service call to a single bulb."""
        self.turn_on(timer_kwargs["entity"], **timer_kwargs["kwargs"])

    def _internal_turn_off(self):
        """Turn off lights using a staggered/stacked delay loop to stabilize Matter networking."""
        self._internal_action = True
        entities = self._get_entities_to_control()
        
        delay = 0.0
        for entity in entities:
            # Injecting staggered timers to prevent simultaneous mDNS / multicast rushes
            self.run_in(self._staggered_turn_off_executor, delay, entity=entity)
            delay += 0.15  # 150 milliseconds gap between each bulb execution
            
        # Clear the internal action shield shortly after the final timer is dispatched
        self.run_in(self._clear_internal_action, delay + 0.5)

    def _staggered_turn_off_executor(self, timer_kwargs):
        """Directly sends the Home Assistant turn_off service call to a single bulb."""
        self.turn_off(timer_kwargs["entity"])

    def _clear_internal_action(self, kwargs):
        """Reset internal flag to allow the app to resume parsing physical user interactions."""
        self._internal_action = False

    def entity_state_callback(self, entity, attribute, old, new, kwargs):
        """Intercept state changes to detect if a human manually overrode the lights."""
        if self._internal_action:
            return

        if old == "off" and new == "on":
            self.manual_override = True
            self.log(f"Manual override enabled. True physical user interaction detected on: {entity}")
        elif old == "on" and new == "off":
            if self.manual_override:
                self.manual_override = False
                self.log(f"Manual override cleared. True physical user interaction detected on: {entity}")

    def _run_apply_state(self, kwargs):
        """Scheduled wrapper to call `apply_light_state` safely off the listener thread."""
        motion = kwargs.get("motion", False)
        try:
            self.apply_light_state(motion=motion)
        except Exception as e:
            self.log(f"Error in scheduled apply_light_state execution loop: {e}", level="ERROR")