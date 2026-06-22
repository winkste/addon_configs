"""
AppDaemon Class: GoveeCombined
Author: AI Collaborator
Version: 2.1

Description:
    A rock-solid lighting controller that manages GU10 groups based on:
    1. Motion: Increases brightness when movement is detected.
    2. Ambient (Sunset): Maintains a base level of light from sunset until a fixed time (22:00).
    3. Manual Bypass (Optional): An input_boolean that stops the automation if turned ON manually.
"""

import appdaemon.plugins.hass.hassapi as hass
import datetime

class GoveeCombined(hass.Hass):
    """Combined controller for motion and ambient lighting. State-callback free to prevent Matter race conditions."""

    def initialize(self):
        """Initialize the App and subscribe to state changes and schedules."""
        # Load configuration arguments
        self.entity_ctrl = self.args.get("entity_ctrl")
        self.motion_sensor = self.args.get("sensor")
        self.manual_bypass = self.args.get("manual_bypass")  # Optional: input_boolean.terrasse_manual_override

        self.off_delay = self.args.get("off_delay", 60)
        self.sunset_offset = self.args.get("sunset_offset", -15)
        self.brightness_motion = self.args.get("brightness_motion", 255)
        self.brightness_ambi = self.args.get("brightness_ambi", 125)

        # Runtime variables
        self.ambi_timer = None
        self.ambi_active = False

        # Register Motion Callbacks
        if self.motion_sensor:
            self.listen_state(self.motion_on_callback, self.motion_sensor, new="on")
            self.listen_state(self.motion_off_callback, self.motion_sensor, new="off", duration=self.off_delay)
        else:
            self.log("No motion sensor specified. Motion features disabled.")

        # Register Sunset
        if self.entity_ctrl:
            self.run_at_sunset(self.sunset_callback, offset=self.sunset_offset * 60)
        else:
            self.error("No entity_ctrl specified. The app has nothing to control.")

    def _is_bypass_active(self):
        """Checks if a manual user bypass is enabled via Home Assistant helper."""
        if self.manual_bypass and self.get_state(self.manual_bypass) == "on":
            return True
        return False

    def _is_real_sun_down(self):
        """Hard validation check against the real Home Assistant sun state."""
        ha_sun_state = self.get_state("sun.sun")
        return ha_sun_state == "below_horizon"

    def motion_on_callback(self, entity, attribute, old, new, kwargs):
        """Handle motion detection."""
        if self._is_bypass_active():
            self.log("Manual bypass active. Ignoring motion event.")
            return

        if not self._is_real_sun_down() and not getattr(self, "_bypass_sunset_test", False):
            return

        self.log(f"Motion detected on {entity}")
        self.run_in(self._run_apply_state, 0, motion=True)

    def motion_off_callback(self, entity, attribute, old, new, kwargs):
        """Handle motion timeout."""
        if self._is_bypass_active():
            return

        if not self._is_real_sun_down() and not getattr(self, "_bypass_sunset_test", False):
            return

        self.log(f"Motion cleared on {entity} (timeout reached)")
        self.run_in(self._run_apply_state, 0, motion=False)

    def sunset_callback(self, kwargs):
        """Handle sunset event to start ambient mode, with solstice protection."""
        if self.get_now_time() >= datetime.time(22, 0, 0):
            self.log("Sunset triggered AFTER 22:00. Skipping Ambient Mode activation for tonight.")
            self.ambi_active = False
            return

        self.log("Sunset triggered: Starting Ambient Mode.")
        self.ambi_active = True

        if not self._is_bypass_active() and self.get_state(self.motion_sensor) == "off":
            self.apply_light_state(motion=False)

        if self.ambi_timer:
            self.cancel_timer(self.ambi_timer)

        self.ambi_timer = self.run_at(self.end_ambient_callback, "22:00:00")

    def end_ambient_callback(self, kwargs):
        """End ambient mode and turn off light if no motion is active."""
        self.log("22:00 reached: Ending Ambient Mode.")
        self.ambi_active = False
        self.ambi_timer = None

        if self._is_bypass_active():
            return

        if self.motion_sensor and self.get_state(self.motion_sensor) == "off":
            self._internal_turn_off()

    def apply_light_state(self, motion=False):
        """Determine the correct brightness based on current state."""
        if not self.entity_ctrl or self._is_bypass_active():
            return

        if motion:
            self.log(f"Setting {self.entity_ctrl} to Motion Brightness ({self.brightness_motion}).")
            self._internal_turn_on(brightness=self.brightness_motion)
        elif self.ambi_active:
            self.log(f"Setting {self.entity_ctrl} to Ambient Brightness ({self.brightness_ambi}).")
            self._internal_turn_on(brightness=self.brightness_ambi)
        else:
            self.log(f"No motion and Ambient Mode inactive. Turning off {self.entity_ctrl}.")
            self._internal_turn_off()

    def _internal_turn_on(self, **kwargs):
        """Turn on the light entity or group directly."""
        self.turn_on(self.entity_ctrl, **kwargs)

    def _internal_turn_off(self):
        """Turn off the light entity or group directly."""
        self.turn_off(self.entity_ctrl)

    def _run_apply_state(self, kwargs):
        """Scheduled wrapper to call apply_light_state safely."""
        motion = kwargs.get("motion", False)
        try:
            self.apply_light_state(motion=motion)
        except Exception as e:
            self.log(f"Error in scheduled apply_light_state execution loop: {e}", level="ERROR")
