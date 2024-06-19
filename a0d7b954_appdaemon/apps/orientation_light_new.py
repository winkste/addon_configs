#from asyncio.windows_events import NULL
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


class OrientLightNew(hass.Hass):
    timer_handle = None
    motion_sensor = None
    entity_ctrl = None
    off_delay = 60
    sun_down_recog = True


    def initialize(self):
        self.timer_handle = None
        # Subscribe to sensors
        if "sensor" in self.args:
            self.motion_sensor = self.args["sensor"]
            self.listen_state(self.motion_on, self.motion_sensor, new = "on")
            self.listen_state(self.motion_off, self.motion_sensor, new = "off")
        else:
            self.log("No sensor specified, doing nothing")
        if "entity_ctrl" in self.args:
            self.entity_ctrl = self.args["entity_ctrl"]
        else:
            self.log("No entity specified, just logging")
        if "delay" in self.args:
            self.off_delay = self.args["delay"]
        else:
            self.off_delay = 60
            self.log("No delay specified, just default 60secs")
        if "sunrec" in self.args:
            self.sun_down_recog = self.args["sunrec"]
        else:
            self.sun_down_recog = True
            self.log("No sun down recognition specified, just default YES")


    def motion_on(self, entity, attribute, old, new, kwargs):
        self.log("Motion detected: {}".format(self.motion_sensor))
        if self.timer_handle != None:
                self.cancel_timer(self.timer_handle)
                self.timer_handle = None
        if (self.sun_down_recog == True and self.sun_down()) or self.sun_down_recog == False:   # check that it is still dark 
            self.turn_on_entity()
    

    def motion_off(self, entity, attribute, old, new, kwargs):
        self.log("Motion off: {}".format(self.motion_sensor))
        if self.timer_handle != None:
            self.cancel_timer(self.timer_handle)
            self.timer_handle = None
        if (self.sun_down_recog == True and self.sun_down()) or self.sun_down_recog == False:
            self.timer_handle = self.run_in(self.timer_timeout, self.off_delay)
        else:
            self.turn_off_entity()


    def timer_timeout(self, kwargs):
        self.turn_off_entity()
    

    def turn_off_entity(self):
        if self.entity_ctrl:
            self.log("Turning {} off".format(self.entity_ctrl))
            self.turn_off(self.entity_ctrl)
    

    def turn_on_entity(self):
        if self.entity_ctrl:
            self.log("Turning {} on".format(self.entity_ctrl))
            self.turn_on(self.entity_ctrl)

