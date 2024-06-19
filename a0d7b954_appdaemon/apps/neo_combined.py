"""
NEO RGB LED combined controller: Motion and Ambient light

App to turn lights on when motion detected then off again after a delay
Additional it will turn on ambi light at a certain delay after sunset to a max time

Use with constraints to activate only for the hours of darkness

Signal chart:
---------------------------------------------------------------------------------------------------
                Single at night         Day           Two activations         Continuous activation
---------------------------------------------------------------------------------------------------
 Motion      :____|----|_____________X__|----|___X__|----|__|----|_______X__|------------|________X
 sun_down    :_|------------------|__X___________X_|---------------------X------------------------X
 timer       :_________|-----|_______X___________X_______|--|____|-----|_X_______________|-----|__X
 light       :____|----------|_______X___________X__|------------------|_X__|------------------|__X
 ambi_time   :_____________________________________________________________________________________

 
---------------------------------------------------------------------------------------------------
                Single at night         Day                
---------------------------------------------------------------------------------------------------
 Motion      :_______XXXXXXXX_____________X______
 sun_down    :_|------------------|______________
 rand_delay  :_|---|
 timer2      :_____|----------|__________________
 light       :_____|----------|__________________
 ambi_time   :_____|----------|__________________

motion state on:
    check ambi_time
    check sun state:
        if not ambi_time
            turn light on
            timer stop

motion state off:
    timer start

timer timed out:
    if not ambi_time
        turn light off

Args:

sensor: binary sensor or a list of sensors to use as trigger
entity_ctrl: list of entity to control when detecting motion, can be a light, script, 
               scene or anything else that can be turned on/off
Release Notes

Version 1.0:
    Initial Version adapted from: 
    https://github.com/AppDaemon/appdaemon/blob/dev/conf/example_apps/motion_lights.py
"""

from appdaemon.appdaemon import AppDaemon
import appdaemon.plugins.hass.hassapi as hass


class NeoCombined(hass.Hass):
    """Neo RGB light combined ambient and motion light
    """

    def __init__(self, ad: AppDaemon, name, logging, args, config, app_config, global_vars):
        """This is the constructor initialize function for this app class
        """
        super().__init__(ad, name, logging, args, config, app_config, global_vars)
        self.ambi_timer = None
        self.motion_sensor = None
        self.entity_ctrl = None
        self.off_delay = 60
        self.ambi_time = False
        self.sunset_offset = -15
        self.brightness_motion = 125
        self.brightness_ambi = 125

    def initialize(self):
        """This function initializes the appdeamon task.
        """
        if "sensor" in self.args:
            self.motion_sensor = self.args["sensor"]
            # subscribe callbacks to sensor state events
            self.listen_state(self.motion_on_callback, self.motion_sensor, new = "on")
            self.listen_state(self.motion_off_callback, self.motion_sensor, new = "off", duration=self.off_delay)
        else:
            self.log("No sensor specified, motion detection function not available")
        if "entity_ctrl" in self.args:
            self.entity_ctrl = self.args["entity_ctrl"]
            # subscribe callback to sunset event
            self.run_at_sunset(self.sunset_callback, offset = self.sunset_offset * 60)
        else:
            self.log("No entity specified, just logging")


    def motion_on_callback(self, _entity, _attribute, _old, _new, _kwargs):
        """Callback for motion state "on" detection
        """
        self.log(f"Motion detected: {self.motion_sensor}")
        if self.sun_down():   # check that it is dark
            self.turn_on_motion_light()


    def motion_off_callback(self, _entity, _attribute, _old, _new, _kwargs):
        """Callback for motion state "off" detection
        """
        self.log(f"Motion off: {self.motion_sensor}")
        self.turn_off_motion_light()


    def turn_on_motion_light(self):
        """Function to turn on motion light
        """
        if not self.ambi_time:
            self.log(f"Turning {self.entity_ctrl} on for motion")
            if self.entity_ctrl is not None:
                self.turn_on(self.entity_ctrl, brightness = self.brightness_motion)


    def turn_off_motion_light(self):
        """Function to turn of motion light
        """
        if not self.ambi_time:
            self.log(f"Turning {self.entity_ctrl} off for motion")
            if self.entity_ctrl is not None:
                self.turn_off(self.entity_ctrl)


    def sunset_callback(self, _kwargs):
        """Callback function for sunset event
        """
        self.log("--- Sunset detected ----")
        self.ambi_time = True
        self.turn_on_ambi_light()
        if self.ambi_timer is not None:
            if self.timer_running(self.ambi_timer):
                self.cancel_timer(self.ambi_timer)
            self.ambi_timer = None
        self.ambi_timer = self.run_at(self.ambi_timer_callback, "22:00:00")


    def ambi_timer_callback(self, _kwargs):
        """Ambient light timer callback function
        """
        self.ambi_time = False
        self.log("Ambient timer callback")
        self.turn_off_ambi_light()
        if self.ambi_timer is not None:
            self.ambi_timer = None


    def turn_on_ambi_light(self):
        """Turn on the ambient light
        """
        if self.entity_ctrl is not None:
            self.turn_on(self.entity_ctrl, brightness = self.brightness_ambi)
            self.log(f"Turned on {self.entity_ctrl} for ambi")


    def turn_off_ambi_light(self):
        """Turn off the ambient light
        """
        if self.entity_ctrl is not None:
            self.turn_off(self.entity_ctrl)
            self.log(f"Turned off {self.entity_ctrl} for ambi")
