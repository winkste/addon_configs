"""
NEO RGB LED combined temperature-aware controller: Motion, Ambient light, and Temperature-based color

App to turn lights on when motion detected then off again after a delay.
Additionally it will turn on ambient light at sunset and adjust the light color from cold white
to warm white based on a temperature sensor input.

Args:
    sensor: binary sensor or a list of sensors to use as trigger
    temp_sensor: temperature sensor entity to use for color temperature mapping
    entity_ctrl: list of entity to control when detecting motion, can be a light, script,
                 scene or anything else that can be turned on/off
    cold_kelvin: optional cold white color temperature in kelvin (default 6500)
    warm_kelvin: optional warm white color temperature in kelvin (default 2700)
    min_temp: optional minimum temperature for mapping (default 0)
    max_temp: optional maximum temperature for mapping (default 25)

Release Notes

Version 1.0:
    Initial Version based on neo_combined.py
"""

from appdaemon.appdaemon import AppDaemon
import appdaemon.plugins.hass.hassapi as hass


class NeoCombinedTemp(hass.Hass):
    """Neo RGB light combined ambient and motion light with temperature-based white color."""

    def initialize(self):
        """Initialize the AppDaemon app."""
        self.ambi_timer = None
        self.motion_sensor = None
        self.entity_ctrl = None
        self.temp_sensor = None
        self.off_delay = self.args.get("off_delay", 60)
        self.ambi_time = False
        self.sunset_offset = self.args.get("sunset_offset", -15)
        self.brightness_motion = self.args.get("brightness_motion", 125)
        self.brightness_ambi = self.args.get("brightness_ambi", 125)
        self.cold_kelvin = self.args.get("cold_kelvin", 6500)
        self.warm_kelvin = self.args.get("warm_kelvin", 2700)
        self.min_temp = self.args.get("min_temp", 0.0)
        self.max_temp = self.args.get("max_temp", 25.0)

        if "sensor" in self.args:
            self.motion_sensor = self.args["sensor"]
            self.listen_state(self.motion_on_callback, self.motion_sensor, new="on")
            self.listen_state(self.motion_off_callback, self.motion_sensor, new="off", duration=self.off_delay)
        else:
            self.log("No sensor specified, motion detection function not available")

        if "entity_ctrl" in self.args:
            self.entity_ctrl = self.args["entity_ctrl"]
            self.run_at_sunset(self.sunset_callback, offset=self.sunset_offset * 60)
        else:
            self.log("No entity specified, just logging")

        if "temp_sensor" in self.args:
            self.temp_sensor = self.args["temp_sensor"]
        else:
            self.log("No temp_sensor specified, color temperature will use default cold/warm values")

    def motion_on_callback(self, _entity, _attribute, _old, _new, _kwargs):
        """Callback for motion state "on" detection."""
        self.log(f"Motion detected: {self.motion_sensor}")
        if self.sun_down():
            self.turn_on_motion_light()

    def motion_off_callback(self, _entity, _attribute, _old, _new, _kwargs):
        """Callback for motion state "off" detection."""
        self.log(f"Motion off: {self.motion_sensor}")
        self.turn_off_motion_light()

    def turn_on_motion_light(self):
        """Turn on the controlled light for motion with temperature-based white color."""
        if not self.ambi_time:
            self.log(f"Turning {self.entity_ctrl} on for motion")
            if self.entity_ctrl is not None:
                kwargs = {
                    "brightness": self.brightness_motion,
                    "kelvin": self.get_color_temperature(),
                }
                self.turn_on(self.entity_ctrl, **kwargs)

    def turn_off_motion_light(self):
        """Turn off the controlled light for motion."""
        if not self.ambi_time:
            self.log(f"Turning {self.entity_ctrl} off for motion")
            if self.entity_ctrl is not None:
                self.turn_off(self.entity_ctrl)

    def sunset_callback(self, _kwargs):
        """Callback function for sunset event."""
        self.log("--- Sunset detected ----")
        self.ambi_time = True
        self.turn_on_ambi_light()
        if self.ambi_timer is not None and self.timer_running(self.ambi_timer):
            self.cancel_timer(self.ambi_timer)
            self.ambi_timer = None
        self.ambi_timer = self.run_at(self.ambi_timer_callback, "22:00:00")

    def ambi_timer_callback(self, _kwargs):
        """Ambient light timer callback function."""
        self.ambi_time = False
        self.log("Ambient timer callback")
        self.turn_off_ambi_light()
        self.ambi_timer = None

    def turn_on_ambi_light(self):
        """Turn on the controlled light for ambient lighting."""
        if self.entity_ctrl is not None:
            self.turn_on(self.entity_ctrl, brightness=self.brightness_ambi, kelvin=self.get_color_temperature())
            self.log(f"Turned on {self.entity_ctrl} for ambi")

    def turn_off_ambi_light(self):
        """Turn off the controlled light for ambient lighting."""
        if self.entity_ctrl is not None:
            self.turn_off(self.entity_ctrl)
            self.log(f"Turned off {self.entity_ctrl} for ambi")

    def get_color_temperature(self):
        """Return a color temperature in kelvin based on the configured temperature sensor."""
        temperature = None
        if self.temp_sensor is not None:
            state = self.get_state(self.temp_sensor)
            try:
                temperature = float(state)
            except (TypeError, ValueError):
                self.log(f"Unable to parse temperature from {self.temp_sensor}: {state}")

        if temperature is None:
            self.log("Using default cold white because temperature sensor value is unavailable")
            return self.cold_kelvin

        if temperature <= self.min_temp:
            return self.cold_kelvin
        if temperature >= self.max_temp:
            return self.warm_kelvin

        span = self.max_temp - self.min_temp
        ratio = (temperature - self.min_temp) / span
        kelvin = int(self.cold_kelvin + (self.warm_kelvin - self.cold_kelvin) * ratio)
        self.log(f"Temperature {temperature}°C mapped to {kelvin}K")
        return kelvin
