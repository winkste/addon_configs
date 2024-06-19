import hassapi as hass

#
# Orientation light controller

# App to turn lights on when motion detected then off again after a delay
#
# Use with constraints to activate only for the hours of darkness
#
# Signal chart:
#------------------------------------------------------------------------------------------------------
#                Single at night         Day           Two activations          Continuous activation       
#------------------------------------------------------------------------------------------------------
# Motion      :____|----|_____________X__|----|___X__|----|__|----|_______X__|------------|________X
# sun_down    :_|------------------|__X___________X_|---------------------X------------------------X
# timer       :_________|-----|_______X___________X_______|--|____|-----|_X_______________|-----|__X
# light       :____|----------|_______X___________X__|------------------|_X__|------------------|__X
#
# motion state on:
#   check sun state:
#       turn light on
#       timer stop
#
# motion state off:
#   timer start
#
# timer timed out:
#   turn light off
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


class OrientLight(hass.Hass):

    def initialize(self):
        self.handle = None
        # Subscribe to sensors
        if "sensor" in self.args:
            self.listen_state(self.motion, self.args["sensor"])
        else:
            self.log("No sensor specified, doing nothing")

    def motion(self, entity, attribute, old, new, kwargs):
        if "sensor" in self.args:
            self.log("Motion detected: {}".format(self.args["sensor"]))
        if self.sun_down():   # check that it is still dark 
            if new == "on":
                if "entity_ctrl" in self.args:
                    self.log("Turning {} on".format(self.args["entity_ctrl"]))
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