#
# Alarm Controller
#
# Refer to the API documentation of Appdaemon:
# https://appdaemon.readthedocs.io/en/latest/HASS_API_REFERENCE.html
#
# Description: 
# Controls the alarm handling and reaction
#
# Signal chart:
#---------------------------------------------------------------------------------------------------
#                                    Alarm                      Home
#---------------------------------------------------------------------------------------------------
# armed_away:_______________|-----------------------------|___|------|______________________________
# disarmed  :---------------|_____________________________|---|______|------------------------------
# any_motion:_________________|-|_________|-|___________________|-|_________________________________
# alarm_tmr :_________________|-----|___________________________|----|______________________________
# scene_plr :_______________________|---------------------|_________________________________________
#
#
#
# Args:
#
# alarm_offset = Timeout after motion detected to start alarm sequence player
# away_listener = List of binary sensors that shall trigger alarm if alarm control is in state away
# night_listener = List of binary sensors triggering the alarm in state night
# 
# Signals:
# alarm_control_panel.ha_alarm:
#   - disarmed
#   - arming
#   - armed_away
#   - arm_night
#
# Release Notes
#
# Version 1.0:
#   Initial version of app

ALARM_PANEL = "alarm_control_panel.ha_alarm"
MULTI_LIGHT_SZENES = ["scene.motion_light_red", "scene.motion_light_blue"]
SZENES_OFF = ["scene.motion_light_blue", "scene.motion_light_off", "scene.all_alarm_lights_off"]
SINGLE_ALARM_LIGHTS = "scene.all_alarm_lights"

import hassapi as hass

class AlarmCtrl(hass.Hass):
    alarm_timer = None
    alarm_offset = 30
    alarm_activated = False
    scene_timer = None
    away_listener = None
    night_listener = None
    multi_light_scene_idx = 0

    def initialize(self):
        '''
            Initialization function of class.
        '''
        # handle offset argument for timeout after motion detected
        if "alarm_offset" in self.args:
            self.alarm_offset = self.args["alarm_offset"]
        else:
            self.alarm_offset = 30
        
        # listen to alarm control panel for state changes armed_away and disarmed
        self.listen_state(self._alarm_control, ALARM_PANEL)

        # argument list for listeners used when away
        if "away_listener" in self.args:
            self.away_listener = self.args["away_listener"]
            for entity in self.away_listener:
                self.listen_state(self._away_alarm_listener, entity, new = "on")
        else:
            self.log("No parameters found for away alarm")

        # argument list for listeners used when night
        if "night_listener" in self.args:
            self.night_listener = self.args["night_listener"]
            for entity in self.night_listener:
                self.listen_state(self._night_alarm_listener, entity, new = "on")
        else:
            self.log("No parameters found for night alarm")           

        self.log("alarm controller initialized...")

    def _alarm_control(self, entity, attribute, old, new, kwargs):
        '''
            Callback function for changes of the alarm control panel.
        '''
        self.log(f"alarm controller state changed from: {old} to: {new}")
        if new == "armed_away":
            pass
        if new == "arm_night":
            pass
        elif new == "arming":
            pass
        elif new == "disarmed":
            self._stop_alarm_sequence()
        else:
           self.log(f"alarm controller unexpected state change from: {old} to: {new}") 

    def _stop_alarm_sequence(self):
        '''
            Function that stops all timer and turns light of
        '''
        self.alarm_activated = False
        if None != self.alarm_timer:
            self.cancel_timer(self.alarm_timer)
        for scene in SZENES_OFF:
            self.turn_on(scene)
        if None != self.scene_timer:
            self.cancel_timer(self.scene_timer)   
        self.log("alarm controller alarm sequence deactivated")
    
    def _away_alarm_listener(self, entity, attribute, old, new, kwargs):
        '''
            Callback for all sensors detecting event at "armed_away"
        '''
        if self.get_state(ALARM_PANEL) == "armed_away":
            if False == self.alarm_activated:
                self.log(f"alarm controller away listener, event detected by: {entity}, start alarm sequence")  
                self.alarm_activated = True
                self.alarm_timer = self.run_in(self._start_alarm, self.alarm_offset) 

    def _night_alarm_listener(self, entity, attribute, old, new, kwargs):
        '''
            Callback for all sensors detecting event at "night_arm"
        '''
        if self.get_state(ALARM_PANEL) == "night_arm":
            if False == self.alarm_activated:
                self.log(f"alarm controller away listener, event detected by: {entity}, start alarm sequence")  
                self.alarm_activated = True
                self.alarm_timer = self.run_in(self._start_alarm, self.alarm_offset) 
     
    def _start_alarm(self, kwargs):
        '''
            Callback function for alarm start timer.
        '''
        if None != self.alarm_timer:
            self.cancel_timer(self.alarm_timer)
        self.log("alarm controller alarm started")
        self.turn_on(SINGLE_ALARM_LIGHTS)
        self.turn_on(MULTI_LIGHT_SZENES[self.multi_light_scene_idx])
        self.multi_light_scene_idx = (self.multi_light_scene_idx + 1) % len(MULTI_LIGHT_SZENES)
        self.scene_timer = self.run_in(self._toggle_multi_light, 1)
    
    def _toggle_multi_light(self, kwargs):
        '''
            This function toggles the multi light szenes
        '''
        if True == self.alarm_activated:
            self.turn_on(MULTI_LIGHT_SZENES[self.multi_light_scene_idx])
            self.multi_light_scene_idx = (self.multi_light_scene_idx + 1) % len(MULTI_LIGHT_SZENES)
            self.scene_timer = self.run_in(self._toggle_multi_light, 1)
