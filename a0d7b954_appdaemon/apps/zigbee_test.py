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

#    data = 
#    {
#        'device_ieee': '00:12:4b:00:25:04:6d:0b', 
#        'unique_id': '00:12:4b:00:25:04:6d:0b:1:0x0006', 
#        'device_id': 'fd373c39d91c35f8fd5f0f64fa8a7ac1', 
#        'endpoint_id': 1, 
#        'cluster_id': 6, 
#        'command': 'toggle', 
#        'args': [], 
#        'metadata': 
#        {
#            'origin': 'LOCAL', 
#            'time_fired': '2022-02-03T05:21:27.676250+00:00', 
#            'context': 
#            {
#                'id': '711b634b0cd574f5c746ef0b4967f4ba', 
#                'parent_id': None, 
#                'user_id': None
#                }
#            }
#        }
#    }

class ZigbeeTest(hass.Hass):

    def initialize(self):
        self.listen_event(self.event_hdl, "zha_event")

    def event_hdl(self, event_name, data, kwargs):
        if data['device_ieee'] == '00:12:4b:00:25:04:6d:0b':
            #self.log(f"Event detected from device: {data['device_ieee']}")
            #self.log(f"Event command: {data['command']}")

            if data['command'] == 'toggle':
                self.log(f"Toggle the light")
            elif data['command'] == 'on':
                self.log(f"Turn on the light")
            elif data['command'] == 'off':
                self.log(f"Turn off the light")
            else:
                self.log(f"Unexpected command")
        else:
            self.log(f"Event from new device detected: {event_name}, event data: {data}")
