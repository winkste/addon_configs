"""
Extractor Hood Control

App that turns the extractor hood power plug only on when the a dedicated window is opened.
This shall prevent that the extractor hood in the kitchen extracts exhaust fumes from the open
fire oven.

Signal chart:
---------------------------------------------------------------------------------------------------
                    Window open   Window closed        Window battery sensor empty    
---------------------------------------------------------------------------------------------------
 window_open  :____|-----------|___________________________________________________________________
 power_plug   :____|-----------|____________________|----------------------------------------------
 window_batt  :____|--------------------------------|______________________________________________ 
---------------------------------------------------------------------------------------------------
  
window on state:
    if not battery empty:
        turn off power plug

window of state:
    turn on power plug

timer timed out:
    check battery state
    if battery empty:
        turn on power plug

Args:

sensor: binary sensor or a list of sensors to use as trigger
entity_ctrl: list of entity to control when detecting motion, can be a light, script, 
               scene or anything else that can be turned on/off
batt_sensor: sensor data that can be zero
Release Notes

Version 1.0:
    Initial Version adapted from: 
    https://github.com/AppDaemon/appdaemon/blob/dev/conf/example_apps/motion_lights.py
"""

from appdaemon.appdaemon import AppDaemon
import appdaemon.plugins.hass.hassapi as hass


class ExtractHoodCtrl(hass.Hass):
    """Extract hood window control
    """

    def __init__(self, ad: AppDaemon, name, logging, args, config, app_config, global_vars):
        """This is the constructor initialize function for this app class
        """
        super().__init__(ad, name, logging, args, config, app_config, global_vars)
        self.window_sensor = None
        self.power_plug = None
        self.batt_sensor = None
        self.window_control_enabled = False
        self.battery_fill_state = 0
        self.MIN_BATT_FILL_STATE = 10


    def initialize(self):
        """This function initializes the appdeamon task.
        """
        # Input Parameter Handling
        # Check if sensor is available and register callbacks for state changes
        if "sensor" in self.args:
            self.window_sensor = self.args["sensor"]
            # subscribe callbacks to sensor state events
            self.listen_state(self.window_open_callback, self.window_sensor, new = "on")
            self.listen_state(self.window_closed_callback, self.window_sensor, new = "off")
        else:
            self.log("No sensor specified, window detection function not available")
        # Check if entity is available, else just logging mode active
        if "entity_ctrl" in self.args:
            self.power_plug = self.args["entity_ctrl"]
            # check if window sensor is available, if not, turn directly on
            if self.window_sensor is None:
                self.turn_on_power_plug()
        else:
            self.log("No entity specified, just logging")
        # Check if battery sensor is available
        self.window_control_enabled = False
        if "batt_sensor" in self.args:
            self.batt_sensor = self.args["batt_sensor"]
            # register callback for battery change updates
            self.listen_state(self.batt_change_callback, self.batt_sensor)
            # read initial state and based on the fill rate enable control
            self.battery_fill_state = int(self.get_state(self.batt_sensor))
            self.log(f"Initial Batt state: {self.battery_fill_state}%")
            if self.battery_fill_state > self.MIN_BATT_FILL_STATE:
                self.window_control_enabled = True
                self.log(f"Initial Battery fill state is above min. value.")


    def window_open_callback(self, _entity, _attribute, _old, _new, _kwargs):
        """Callback for window state "on" detection, means window open
        """
        self.log(f"Window open: {self.window_sensor}, window control state: {self.window_control_enabled}")
        self.turn_on_power_plug()


    def window_closed_callback(self, _entity, _attribute, _old, _new, _kwargs):
        """Callback for window state "off" detection, menas window closed
        """
        self.log(f"Window closed: {self.window_sensor}, window control state: {self.window_control_enabled}")
        if self.window_control_enabled is True:
            self.turn_off_power_plug()


    def turn_on_power_plug(self):
        """Function to turn on power plug
        """
        self.log(f"Turning {self.power_plug} on")
        if self.power_plug is not None:
            self.turn_on(self.power_plug)


    def turn_off_power_plug(self):
        """Function to turn off power plug
        """
        self.log(f"Turning {self.power_plug} off")
        if self.power_plug is not None:
            self.turn_off(self.power_plug)


    def batt_change_callback(self, entity, attribute, old, new, kwargs):
        """This function is a callback on battery state filling
        """
        self.log(f"Battery changed: {self.batt_sensor}. Old: {int(old)} -> New: {int(new)}")
        self.battery_fill_state = int(new)
        if self.battery_fill_state < self.MIN_BATT_FILL_STATE: # validate battery level
            # battery level to low, turn on the power plug and disable window control
            self.window_control_enabled = False
            self.log(f"Window control disabled because of battery level, change battery!")
            self.turn_on_power_plug()
        else:
            if self.window_control_enabled is False:
                self.window_control_enabled = True
                self.log(f"Window control enabled, battery level ok!")
