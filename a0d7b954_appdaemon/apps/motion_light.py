import hassapi as hass

#
# Motion light controller
#
# App to turn lights on when motion detected then off again after a delay
#
# Use with constraints to activate only for the hours of darkness
#
# Args:
#
# sensor: binary sensor to use as trigger
# entity_ctrl: entity to control when detecting motion, can be a light, script, 
#               scene or anything else that can be turned on/off
# delay: amount of time after turning on to turn off again. If not specified defaults 
#               to 60 seconds.
#
# Release Notes
#
# Version 1.0:
#   Initial Version adapted from: 
#   https://github.com/AppDaemon/appdaemon/blob/dev/conf/example_apps/motion_lights.py


class MotionLight(hass.Hass):

    def initialize(self):
        self.handle = None
        # Subscribe to sensors
        if "sensor" in self.args:
            self.listen_state(self.motion, self.args["sensor"])
        else:
            self.log("No sensor specified, doing nothing")

    def motion(self, entity, attribute, old, new, kwargs):
        if self.sun_down():   # check that it is still dark 
            if new == "on":
                if "entity_ctrl" in self.args:
                    self.log("Motion detected: turning {} on".format(self.args["entity_ctrl"]))
                    self.turn_on(self.args["entity_ctrl"])
                if "delay" in self.args:
                    delay = self.args["delay"]
                else:
                    delay = 60
                self.cancel_timer(self.handle)
                self.handle = self.run_in(self.light_off, delay)

    def light_off(self, kwargs):
        if "entity_ctrl" in self.args:
            self.log("Turning {} off".format(self.args["entity_ctrl"]))
            self.turn_off(self.args["entity_ctrl"])