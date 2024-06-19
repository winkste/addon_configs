"""
Ambient light controller

Refer to the API documentation of Appdaemon:
https://appdaemon.readthedocs.io/en/latest/HASS_API_REFERENCE.html

Args:

Description:
App to turn lights on when (sunset - offset * 60sec) and turns off at offTime
Use with constraints to activate only for the hours of darkness

Signal chart:
---------------------------------------------------------------------------------------------------
                Check sunset     Day    sun_set - offset       offTime event
---------------------------------------------------------------------------------------------------
morning evt :____|---|____________________________________________________________________________
sun_set     :_________________________________|---------------------------------------------------
offset      :_____________________________|---|___________________________________________________
light       :_____________________________|---------------------|_________________________________
offTime     :___________________________________________________|---|_____________________________


Args:

offset:       positive or negative offset to sunset
entity_ctrl:  entities to control, can be a light, script, 
              scene or anything else that can be turned on/off
switch:       additional switch to control light

Release Notes

Version 1.0:
  Initial version of app
"""
from appdaemon.appdaemon import AppDaemon
import appdaemon.plugins.hass.hassapi as hass

class AmbientLight(hass.Hass):
    """Ambient light control class
    """

    def __init__(self, ad: AppDaemon, name, logging, args, config, app_config, global_vars):
        """Class constructor
        """
        super().__init__(ad, name, logging, args, config, app_config, global_vars)

        self.sunset_offset = -30
        self.timer_handle = None
        self.switch = None
        self.entity_ctrl = None

    def initialize(self):
        """App initialization function
        """
        if "offset" in self.args:
            self.sunset_offset = self.args["offset"]
        else:
            self.sunset_offset = -30

        if "switch" in self.args:
            self.switch = self.args["switch"]
            self.listen_state(self.switch_trigger_callback, self.switch)
        else:
            self.log("ambi light no switch detected...")

        if "entity_ctrl" in self.args:
            self.entity_ctrl = self.args["entity_ctrl"]
            self.log("ambi light application initialized...")
            self.run_at_sunset(self.sunset_callback, offset = self.sunset_offset * 60)
        else:
            self.log("ambi light no entity detected...")

    def sunset_callback(self, _kwargs):
        """Sunset event callback function
        """
        if self.entity_ctrl is not None:
            self.log(f"Turning {self.entity_ctrl} on")
            self.turn_on(self.entity_ctrl)
            self.timer_handle = None
            self.timer_handle = self.run_at(self.light_timer_callback, "22:00:00")

    def light_timer_callback(self, _kwargs):
        """Timer callback
        """
        if self.entity_ctrl is not None:
            self.log(f"Turning {self.entity_ctrl} off")
            self.turn_off(self.entity_ctrl)
            self.timer_handle = None

    def switch_trigger_callback(self, _entity, _attribute, old, new, _kwargs):
        """Callback function for switch trigger
        """
        if self.switch is not None:
            self.log(f"Trigger detected: {self.switch}")
            self.log(f"Trigger from {old} to {new}")
            if self.entity_ctrl is not None:
                entity_state = self.get_state(self.entity_ctrl)
                self.log(f"{self.entity_ctrl} is in state: {entity_state}")
                if old == "off" and new == "on":
                    if entity_state == "off":
                        self.turn_on(self.entity_ctrl)
                    else:
                        self.turn_off(self.entity_ctrl)
