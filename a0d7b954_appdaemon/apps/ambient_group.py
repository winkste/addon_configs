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
lights:       entities to control, can be a light, script, 
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
    def initialize(self):
        """App initialization function
        """
        self.sunset_offset = -30
        self.timer_handle = None
        self.switch = None
        self.lights = None

        if "offset" in self.args:
            self.sunset_offset = self.args["offset"]
        else:
            self.sunset_offset = -30

        if "switch" in self.args:
            self.switch = self.args["switch"]
            self.listen_state(self.switch_trigger_callback, self.switch)
        else:
            self.log("ambi light no switch detected...")

        if "lights" in self.args:
            self.lights = self.args["lights"]
            self.log("ambi light application initialized...")
            self.run_at_sunset(self.sunset_callback, offset = self.sunset_offset * 60)
        else:
            self.log("ambi light no entity detected...")

    def sunset_callback(self, _kwargs):
        """Sunset event callback function
        """
        self.turn_on_lights()
        self.timer_handle = None
        self.timer_handle = self.run_at(self.light_timer_callback, "22:00:00")

    def light_timer_callback(self, _kwargs):
        """Timer callback
        """
        self.turn_off_lights()
        self.timer_handle = None

    def switch_trigger_callback(self, _entity, _attribute, old, new, _kwargs):
        """Callback function for switch trigger
        """
        if self.switch is not None:
            self.log(f"Trigger detected: {self.switch}")
            self.log(f"Trigger from {old} to {new}")
            if old == "off" and new == "on":
                self.turn_on_lights()
            else:
                self.turn_off_lights()
            else:
                self.log(f"Error with entity: {light}.")


    def turn_off_lights(self):
        """Function to turn lights off
        """
        if self.lights is not None:
            for light in self.lights:
                if light is not None:
                    self.log(f"Turning {light} off")
                    self.turn_off(light)
                else:
                    self.log(f"Error with entity: {light}.")
    

    def turn_on_lights(self):
        """Function to turn lights on
        """
        if self.lights is not None:
            for light in self.lights:
                if light is not None:
                    self.log(f"Turning {self.light} on")
                    self.turn_on(self.light)
                else:
                    self.log(f"Error with entity: {self.light}.")              
