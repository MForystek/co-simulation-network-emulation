import time


class UFLSHandler:
    def __init__(self):
        self._NOMINAL_SPEED = 377
        self._NOMINAL_FREQ = 60
        
        self._freq_level_1 = 59.5
        self._freq_level_2 = 59.3
        self._freq_level_3 = 59.1
        self._freq_level_4 = 58.9
        self._freq_level_5 = 59.5
        
        self._shedding_level_1 = 7.0
        self._shedding_level_2 = 7.0
        self._shedding_level_3 = 7.0
        self._shedding_level_4 = 7.0
        # self._shedding_level_5 = 2.5
        
        self._prev_freq = self._NOMINAL_FREQ
        # self._freq_from_10_sec = self._NOMINAL_FREQ
        self._percentage_of_load_to_shed = 0.0
    
    
    def get_percentage_of_load_to_shed(self, visitor_index_and_value):
        # taking speed of 3rd generator
        speed = visitor_index_and_value[2][1]
        freq = speed / self._NOMINAL_SPEED * self._NOMINAL_FREQ
        prev_freq = 0.0
        
        self._percentage_of_load_to_shed = 0.0
        
        if (freq < self._freq_level_1 and prev_freq < self._freq_level_1):
            self._percentage_of_load_to_shed += self._shedding_level_1
        if (freq < self._freq_level_2 and prev_freq < self._freq_level_2):
            self._percentage_of_load_to_shed += self._shedding_level_2
        if (freq < self._freq_level_3 and prev_freq < self._freq_level_3):
            self._percentage_of_load_to_shed += self._shedding_level_3
        if (freq < self._freq_level_4 and prev_freq < self._freq_level_4):
            self._percentage_of_load_to_shed += self._shedding_level_4
        # if (freq < self._freq_level_5 and freq_from_10_sec < self._freq_level_5):
        #     self._percentage_of_load_to_shed += self._shedding_level_5    
        self._prev_freq = freq    
        return self._percentage_of_load_to_shed