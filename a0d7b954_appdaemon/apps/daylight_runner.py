"""
This is the daylight runner application class.

It checks for sun rise and activate a list of entities and stops it on sun down.
There will be a sun rise delay and a sun down per time to ensure entities are off. This
app can be used to control entities only running when daylight is available. Means indirect
to enough power coming from solar panels

Signal chart:
---------------------------------------------------------------------------------------------------
                                    Day                         Night                   Day
---------------------------------------------------------------------------------------------------
 sun_rise    :____|-------------------------------------|_______________________|------------------
 sr_delay    :____|---|_________________________________________________________|---|______________
 entity_on   :________|---------------------------|_________________________________|--------------
 sd_pre      :____________________________________||______________________-________________________
 sun_down    :----|_____________________________________|-----------------------|__________________


Args:

entity_ctrl: list of entity to control when detecting motion, can be a light, script, 
               scene or anything else that can be turned on/off

Release Notes

Version 1.0:
    Initial Version adapted from: 
    https://github.com/AppDaemon/appdaemon/blob/dev/conf/example_apps/motion_lights.py
"""

from appdaemon.appdaemon import AppDaemon
import appdaemon.plugins.hass.hassapi as hass


class DayLightRunner(hass.Hass):
    """Daylight activated devices.
    """

    def __init__(self, ad: AppDaemon, name, logging, args, config, app_config, global_vars):
        """This is the constructor initialize function for this app class
        """
        super().__init__(ad, name, logging, args, config, app_config, global_vars)
        self.sunrise_delay_in_min = 60
        self.sunset_delay_pre_time_in_min = 60
        self.entity_ctrl = None

    def initialize(self):
        """This function initializes the appdeamon task.
        """
        if "entity_ctrl" in self.args:
            self.entity_ctrl = self.args["entity_ctrl"]
            # subscribe callback to sunset event
            self.run_at_sunset(self.sunset_callback,
                                offset = self.sunset_delay_pre_time_in_min * 60)
            self.run_at_sunrise(self.sunrise_callback,
                                offset = self.sunrise_delay_in_min * 60)
            # set the initial state of the entities based on current night/day
            if self.sun_down():
                self.turn_entities_off()
            else:
                self.turn_entities_on()
        else:
            self.log("No entity specified, just logging")

    def sunset_callback(self, _kwargs):
        """Callback function for sunset event
        """
        self.log("--- Sunset detected ----")
        self.turn_entities_off()

    def sunrise_callback(self, _kwargs):
        """Callback function for sunrise event
        """
        self.log("--- Sunrise detected ----")
        self.turn_entities_on()

    def turn_entities_on(self):
        """Turn on the entities
        """
        if self.entity_ctrl is not None:            
            for entity in self.entity_ctrl:
                self.log(f"Turned on {entity} for sunrise")
                self.turn_on(entity)

    def turn_entities_off(self):
        """Turn off the entities
        """
        if self.entity_ctrl is not None:
            for entity in self.entity_ctrl:
                self.turn_off(entity)
                self.log(f"Turned off {entity} for sunset")
