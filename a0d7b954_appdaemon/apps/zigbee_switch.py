#
# Zigbee switch controller
#
# Refer to the API documentation of Appdaemon:
# https://appdaemon.readthedocs.io/en/latest/HASS_API_REFERENCE.html
#
# Description: 
# This controller reacts on a zigbee switch event (sonoff). Events to react on:
# - on:     turns all lights on
# - off:    turns all lights off
# - toggle: toggle all lights
#
# Args:
#
# switch:       zigbee address of switch, as this is an event, it has to listen 
#               to all "zha_event" events and selects then the correct switch
#               address
# entity_ctrl:  entities to control, can be a light, script, 
#               scene or anything else that can be turned on/off
#
# Release Notes
#
# Version 1.0:
#   Initial version of app

import hassapi as hass


class ZigbeeSwitch(hass.Hass):
  switch = None
  entity_ctrl = None


  def initialize(self):
    # read arguments and store to object variables
    self.entity_ctrl = self.args["entity_ctrl"]
    self.switch = self.args["switch"]

    if "switch" not in self.args:
      self.log("zigbee switch no switch detected...")
    elif "entity_ctrl" not in self.args:
      self.log("zigbee switch no entity control detected...") 
    else:  
      self.switch = self.args["switch"]
      self.entity_ctrl = self.args["entity_ctrl"]
      self.listen_event(self.event_hdl, "zha_event")
      self.log("zigbee switch controller initialized...")

  def event_hdl(self, event_name, data, kwargs):
    if data['device_ieee'] == self.switch:
      if data['command'] == 'toggle':
        self._toggle_entities()
      elif data['command'] == 'on':
        self._turn_entities_on()
      elif data['command'] == 'off':
          self._turn_entities_off()
      else:
          self.log(f"Unexpected command")
    else:
      self.log(f"Event from new device detected: {event_name}, event data: {data}") 
    
  def _turn_entities_on(self):
    self.log(f"Turn on the entities")
    for entity in self.entity_ctrl:
      self.log("Turn on: " + entity)
      self.turn_on(entity) # turn on the entity
  
  def _turn_entities_off(self):
    self.log(f"Turn off the entities")
    for entity in self.entity_ctrl:
      self.log("Turn off: " + entity)
      self.turn_off(entity) # turn off the entity
  
  def _toggle_entities(self):
    self.log(f"Toggle the entities")
    for entity in self.entity_ctrl:
      self.log("Toggle: " + entity)
      self.toggle(entity) # toggle the entity
