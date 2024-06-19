import hassapi as hass

#
# Carport light controller
#
# App to turn lights on when motion detected then off again after a delay
#
# Use with constraints to activate only for the hours of darkness
#
# Args:
#
# delay: amount of time after turning on to turn off again. If not specified defaults 
#               to 60 seconds.
#
# Release Notes
#
# Version 1.0:
#   Initial Version adapted from: 
#   https://github.com/AppDaemon/appdaemon/blob/dev/conf/example_apps/motion_lights.py


class CarportLight(hass.Hass):

    def initialize(self):
        self.handle = None
        # Subscribe to sensors
        if "sensor" in self.args:
            for sensor in self.args['sensor']:
                self.listen_state(self.motion, sensor)
        else:
            self.log("No sensor specified, doing nothing")

    def motion(self, entity, attribute, old, new, kwargs):
        if self.sun_down():   # check that it is still dark 
            if new == "on":
                if "entity_ctrl" in self.args:
                    for entity in self.args['entity_ctrl']:
                        self.log("Motion detected: turning {} on".format(entity))
                        self.turn_on(entity)
                if "delay" in self.args:
                    delay = self.args["delay"]
                else:
                    delay = 60
                self.cancel_timer(self.handle)
                self.handle = self.run_in(self.light_off, delay)

    def light_off(self, kwargs):
        if "entity_ctrl" in self.args:
            for entity in self.args['entity_ctrl']:
                self.log("Turning {} off".format(entity))
                self.turn_off(entity)