import appdaemon.plugins.hass.hassapi as hass

#
# Night Light Reset controller
#
# Args:
#
# Description: 
# - conumses a list of lights
# - runs once a night and turns off all lights in list
#
#

class NightReset(hass.Hass):

  def initialize(self):
    self.log("night reset controller application initialized...")
    self.run_daily(self.night_reset, "00:00:00")
    self.lights = self.args["lights"]

  def night_reset(self, kwargs):
    self.log(" --- RESET TIME ---")
    for light in self.lights:
      self.log("Resetting: " + light)
      self.turn_off(light) # turn off the light
