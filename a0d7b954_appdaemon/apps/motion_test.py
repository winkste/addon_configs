import appdaemon.plugins.hass.hassapi as hass

#
# Motion Test App
#
# Args:
#

class MotionTest(hass.Hass):

  def initialize(self):
    self.log("motion test application initialized...")
    self.listen_state(self.motion, "binary_sensor.dev101_motion", new = "on")
    #self.listen_state(self.nomotion, "binary_sensor.dev101_motion", new = "off")
    self.listen_state(self.light_state, "light.dev101_r1", new = "on")
    self.timer = None

  def light_state(self, entity, attribute, old, new, kwargs):
    self.log("light 1 on...")

  def motion(self, entity, attribute, old, new, kwargs):
    self.log("motion detected...")
    if self.sun_down():   # check that it is still dark
      if (self.get_state('light.dev101_r1') == "on") and None == self.timer: # check for manual turn on the light
        self.log('motion detected, but light manal turned on')
      else:
        self.turn_on("light.dev101_r1") # turn on the light
        if None != self.timer:  # check if timer is already running, means new motion detected within a timer cycle 
          self.cancel_timer(self.timer) # cancel that timer for restarting
          self.log('cancel timer...')
        self.timer = self.run_in(self.light_off, 10) # start timer to turn of the light with delay
        self.log('timer: ' + str(self.timer))

  def light_off(self, kwargs):
    if self.get_state('binary_sensor.dev101_motion') == "on": # check if sensor is still in motion
      self.timer = self.run_in(self.light_off, 10) # yes, restart timer
      self.log('in light off, motion still detected, restart timer...')
    else:
      self.turn_off("light.dev101_r1") # turn of light
      self.log("light turned off...")
      self.timer = None
