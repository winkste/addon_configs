"""
Weather Monitoring App

Description:
Logs the current weather condition and the daily forecast (precipitation and condition)
every hour to analyze data patterns for future automation triggers.
"""

import appdaemon.plugins.hass.hassapi as hass

class WeatherMonitor(hass.Hass):
    def initialize(self):
        """Initialize function for the monitoring task.
        """
        # Load the weather entity from arguments
        self.weather_entity = self.args.get("weather_entity")
        
        if not self.weather_entity:
            self.log("ERROR: No weather_entity configured in apps.yaml", level="ERROR")
            return

        # Run exactly at the start of every hour (e.g., 14:00, 15:00, etc.)
        self.run_every(self.check_and_log_weather, "now", 60 * 60)
        self.log(f"Weather Monitoring App initialized for {self.weather_entity}. Logging every hour.")

    def check_and_log_weather(self, kwargs):
        """Fetches the daily forecast using the modern service call and logs key metrics.
        """
        # 1. Fetch current state as baseline
        current_state = self.get_state(self.weather_entity)
        
        # 2. Call the modern get_forecasts service
        response = self.call_service(
            "weather/get_forecasts",
            entity_id=self.weather_entity,
            type="daily"
        )

        # Safety check if response is valid
        if not response or self.weather_entity not in response:
            self.log(f"WARNING: Could not fetch forecast data for {self.weather_entity}", level="WARNING")
            return

        forecast_list = response[self.weather_entity].get("forecast", [])
        
        if not forecast_list:
            self.log("WARNING: Forecast list is empty.", level="WARNING")
            return

        # Start generating the log message
        log_msg = f"\n--- WEATHER REPORT FOR {self.weather_entity.upper()} ---"
        log_msg += f"\n[Current State] Condition: {current_state}"

        # Loop through the first 3 days (Today, Tomorrow, Day after tomorrow)
        # to see how the predictions evolve over the hours
        max_days = min(3, len(forecast_list))
        for i in range(max_days):
            day_data = forecast_list[i]
            date_str = day_data.get("datetime", "").split("T")[0] # Extracts just the YYYY-MM-DD part
            condition = day_data.get("condition", "unknown")
            precipitation = day_data.get("precipitation", 0.0)
            
            day_label = "Today" if i == 0 else ("Tomorrow" if i == 1 else "Day After")
            log_msg += f"\n[{day_label} - {date_str}] Condition: {condition} | Precipitation: {precipitation}mm"

        log_msg += "\n----------------------------------------"
        
        # Output everything into the standard AppDaemon log
        self.log(log_msg)