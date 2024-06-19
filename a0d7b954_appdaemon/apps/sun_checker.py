"""Sun state controller

Args:
Description: 
- Runs every sunset and sunrise and logs this event
"""

import appdaemon.plugins.hass.hassapi as hass

class SunChecker(hass.Hass):
    """SunChecker class
    """

    def initialize(self):
        """initialization function
        """
        self.log("sun state controller application initialized...")
        self.run_at_sunrise(self.sunrise_callback)
        self.run_at_sunset(self.sunset_callback)


    def sunrise_callback(self, _kwargs):
        """Callback function for sunrise event

        Args:
            kwargs (_type_): unused
        """
        self.log(" --------- SUNRISE -------------")

    def sunset_callback(self, _kwargs):
        """Callback function for sunset event

        Args:
            kwargs (_type_): unused
        """
        self.log(" --------- SUNSET --------------")