"""
Weather Monitoring App

Description:
Logs the current weather condition and the daily forecast (precipitation and condition)
every hour to analyze data patterns for future automation triggers.
Initializes with an immediate execution check and native plugin service response fetch.
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

        self.log(f"Weather Monitoring App starting for {self.weather_entity}...")

        # Execute immediately via direct function call during init
        self.check_and_log_weather(None)

        # Schedule execution every hour (3600 seconds) starting from the next hour
        self.run_every(self.check_and_log_weather, "now + 3600", 60 * 60)
        
        self.log("Weather Monitoring App successfully initialized and scheduled.")

    def check_and_log_weather(self, kwargs):
        """Fetches the daily forecast using the modern service call and logs key metrics.
        """
        self.log("Fetching current weather report...")
        
        # 1. Fetch current state as baseline
        current_state = self.get_state(self.weather_entity)
        
        # 2. Call the weather/get_forecasts service via AppDaemon's call_service method
        try:
            response = self.call_service(
                "weather/get_forecasts",
                entity_id=self.weather_entity,
                type="daily",
                return_response=True
            )
        except Exception as e:
            self.log(f"ERROR: Service call failed: {e}", level="ERROR")
            self.log("Falling back to attributes parsing...", level="WARNING")
            self._fallback_parse_forecast()
            return

        # Safety check if response is valid
        if not response:
            self.log("WARNING: Service returned empty response. Falling back to attributes.", level="WARNING")
            self._fallback_parse_forecast()
            return

        # Debug: Log the response structure to understand what we're getting
        self.log(f"DEBUG: Service response keys: {response.keys() if isinstance(response, dict) else 'Not a dict'}")
        self.log(f"DEBUG: Full response: {response}")

        # Response structure might be: {"forecast": [...]} or wrapped differently
        forecast_list = response.get("forecast", [])
        
        if not forecast_list:
            self.log("WARNING: Forecast list is empty in service response. Falling back to attributes.", level="WARNING")
            self._fallback_parse_forecast()
            return

        # Start generating the log message
        log_msg = f"\n--- WEATHER REPORT FOR {self.weather_entity.upper()} ---"
        log_msg += f"\n[Current State] Condition: {current_state}"

        # Loop through the first 3 days (Today, Tomorrow, Day after tomorrow)
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

    def _fallback_parse_forecast(self):
        """Fallback: Parse forecast from entity attributes if service call fails
        """
        self.log("DEBUG: Attempting fallback attribute parsing...")
        attrs = self.get_state(self.weather_entity, attribute="all")
        
        if not attrs:
            self.log("ERROR: get_state returned None.", level="ERROR")
            return
        
        self.log(f"DEBUG: Entity all attributes keys: {attrs.keys() if isinstance(attrs, dict) else 'Not a dict'}")
        
        if "attributes" not in attrs:
            self.log("ERROR: No 'attributes' key in entity data.", level="ERROR")
            return
        
        forecast_list = attrs["attributes"].get("forecast", [])
        current_state = attrs.get("state", "unknown")
        
        self.log(f"DEBUG: Forecast list length from attributes: {len(forecast_list)}")
        
        if not forecast_list:
            self.log("WARNING: No forecast data available in attributes.", level="WARNING")
            # Still try to log current conditions
            log_msg = f"\n--- WEATHER REPORT (CURRENT ONLY) FOR {self.weather_entity.upper()} ---"
            log_msg += f"\n[Current State] Condition: {current_state}"
            log_msg += "\n[Forecast] No forecast data available"
            log_msg += "\n----------------------------------------"
            self.log(log_msg)
            return

        log_msg = f"\n--- WEATHER REPORT (FROM ATTRIBUTES) FOR {self.weather_entity.upper()} ---"
        log_msg += f"\n[Current State] Condition: {current_state}"

        max_days = min(3, len(forecast_list))
        for i in range(max_days):
            day_data = forecast_list[i]
            date_str = day_data.get("datetime", "").split("T")[0] if day_data.get("datetime") else "Unknown"
            condition = day_data.get("condition", "unknown")
            precipitation = day_data.get("precipitation", 0.0)
            
            day_label = "Today" if i == 0 else ("Tomorrow" if i == 1 else "Day After")
            log_msg += f"\n[{day_label} - {date_str}] Condition: {condition} | Precipitation: {precipitation}mm"

        log_msg += "\n----------------------------------------"
        self.log(log_msg)
