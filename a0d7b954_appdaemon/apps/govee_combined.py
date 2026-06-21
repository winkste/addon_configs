"""
AppDaemon Class: GoveeCombined
Author: AI Collaborator
Version: 2.0

Description:
    A robust lighting controller that manages GU10 RGBW/White groups based on:
    1. Motion: Increases brightness when movement is detected.
    2. Ambient (Sunset): Maintains a base level of light from sunset until a fixed time (22:00).
"""

import appdaemon.plugins.hass.hassapi as hass
import datetime

class GoveeCombined(hass.Hass):
    """Combined controller for motion and ambient lighting with strict group-safe lockouts."""

    def initialize(self):
        """Initialize the App and subscribe to state changes and schedules."""
        # Load configuration arguments
        self.entity_ctrl = self.args.get("entity_ctrl")
        self.motion_sensor = self.args.get("sensor")
        
        self.off_delay = self.args.get("off_delay", 60)
        self.sunset_offset = self.args.get("sunset_offset", -15)
        self.brightness_motion = self.args.get("brightness_motion", 255)
        self.brightness_ambi = self.args.get("brightness_ambi", 125)

        # Runtime variables - Always start fresh
        self.ambi_timer = None
        self.ambi_active = False
        self.manual_override = False
        self._internal_action = False

        # Register Motion Callbacks
        if self.motion_sensor:
            self.listen_state(self.motion_on_callback, self.motion_sensor, new="on")
            self.listen_state(self.motion_off_callback, self.motion_sensor, new="off", duration=self.off_delay)
        else:
            self.log("No motion sensor specified. Motion features disabled.")

        # Register Entity State Callback (Only monitor the direct main controlled group)
        if self.entity_ctrl:
            if isinstance(self.entity_ctrl, list):
                for entity in self.entity_ctrl:
                    self.listen_state(self.entity_state_callback, entity)
            else:
                self.listen_state(self.entity_state_callback, self.entity_ctrl)
                
            self.run_at_sunset(self.sunset_callback, offset=self.sunset_offset * 60)
        else:
            self.error("No entity_ctrl specified. The app has nothing to control.")

    def _is_real_sun_down(self):
        """Hard validation check against the real Home Assistant sun state."""
        ha_sun_state = self.get_state("sun.sun")
        return ha_sun_state == "below_horizon"

    def motion_on_callback(self, entity, attribute, old, new, kwargs):
        """Handle motion detection."""
        if not self._is_real_sun_down() and not getattr(self, "_bypass_sunset_test", False):
            return

        self.log(f"Motion detected on {entity}")
        self.run_in(self._run_apply_state, 0, motion=True)

    def motion_off_callback(self, entity, attribute, old, new, kwargs):
        """Handle motion timeout."""
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

        if self.get_state(self.motion_sensor) == "off":
            self.apply_light_state(motion=False)

        if self.ambi_timer:
            self.cancel_timer(self.ambi_timer)

        self.ambi_timer = self.run_at(self.end_ambient_callback, "22:00:00")

    def end_ambient_callback(self, kwargs):
        """End ambient mode and turn off light if no motion is active."""
        self.log("22:00 reached: Ending Ambient Mode.")
        self.ambi_active = False
        self.ambi_timer = None

        if self.motion_sensor and self.get_state(self.motion_sensor) == "off":
            if self.manual_override:
                self.log("Manual override active; keeping light on after ambient mode ends.")
                return
            self._internal_turn_off()

    def apply_light_state(self, motion=False):
        """Determine the correct brightness based on current state."""
        if not self.entity_ctrl:
            return

        if motion:
            self.log(f"Setting {self.entity_ctrl} to Motion Brightness ({self.brightness_motion}).")
            self._internal_turn_on(brightness=self.brightness_motion)
        elif self.ambi_active:
            self.log(f"Setting {self.entity_ctrl} to Ambient Brightness ({self.brightness_ambi}).")
            self._internal_turn_on(brightness=self.brightness_ambi)
        else:
            if self.manual_override:
                self.log(f"Manual override active; leaving {self.entity_ctrl} on.")
                return
            self.log(f"No motion and Ambient Mode inactive. Turning off {self.entity_ctrl}.")
            self._internal_turn_off()

    def _get_entities_to_control(self):
        """Resolve entity_ctrl into individual entities, supporting both lists and single group entities."""
        if isinstance(self.entity_ctrl, list):
            return self.entity_ctrl
            
        members = self.get_state(self.entity_ctrl, attribute="entity_id")
        if isinstance(members, list):
            return members
            
        return [self.entity_ctrl]

    def _internal_turn_on(self, **kwargs):
        """Turn on lights using a staggered/stacked delay loop."""
        self._internal_action = True
        entities = self._get_entities_to_control()
        
        delay = 0.0
        for entity in entities:
            self.run_in(self._staggered_turn_on_executor, delay, entity=entity, kwargs=kwargs)
            delay += 0.15

        # 5 seconds safety shield to let Matter states settle on turn-on
        self.run_in(self._clear_internal_action, 5.0)

    def _staggered_turn_on_executor(self, timer_kwargs):
        """Directly sends the Home Assistant turn_on service call to a single bulb."""
        self.turn_on(timer_kwargs["entity"], **timer_kwargs["kwargs"])

    def _internal_turn_off(self):
        """Turn off lights using a staggered/stacked delay loop."""
        self._internal_action = True
        entities = self._get_entities_to_control()

        delay = 0.0
        for entity in entities:
            self.run_in(self._staggered_turn_off_executor, delay, entity=entity)
            delay += 0.15

        # 30 seconds safety shield to absorb Matter asynchronous feedback ripples on turn-off
        self.run_in(self._clear_internal_action, 30.0)

    def _staggered_turn_off_executor(self, timer_kwargs):
        """Directly sends the Home Assistant turn_off service call to a single bulb."""
        self.turn_off(timer_kwargs["entity"])

    def _clear_internal_action(self, kwargs):
        """Reset internal flag."""
        self._internal_action = False

    def entity_state_callback(self, entity, attribute, old, new, kwargs):
        """Intercept state changes to detect if a human manually overrode the lights."""
        if self._internal_action:
            return

        # Only listen to the main group, ignore individual bulb entities
        if entity != self.entity_ctrl and not isinstance(self.entity_ctrl, list):
            return

        if old == "off" and new == "on":
            self.manual_override = True
            self.log(f"Manual override enabled. True physical user interaction detected on: {entity}")
        elif old == "on" and new == "off":
            if self.manual_override:
                self.manual_override = False
                self.log(f"Manual override cleared. True physical user interaction detected on: {entity}")

    def _run_apply_state(self, kwargs):
        """Scheduled wrapper to call apply_light_state safely."""
        motion = kwargs.get("motion", False)
        try:
            self.apply_light_state(motion=motion)
        except Exception as e:
            self.log(f"Error in scheduled apply_light_state execution loop: {e}", level="ERROR")
