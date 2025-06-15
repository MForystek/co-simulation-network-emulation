import threading
import time

from cosim.mylogging import getLogger


_log = getLogger(__name__, "logs/LFCHandler.log")


class LFCHandler:
    def __init__(self):   
        self._timer_lock = threading.Lock()
        self._vars_lock = threading.Lock()
         
        # LFC parameters
        self._K_I = 0.005
        self._base_rotor_speed = 377
        self._beta = 20
        
        # LFC variables
        self._reset_controller_vars()
        
        controller_reset_handler = threading.Thread(
        target=self._reset_controller_when_no_connection, daemon=True)
        controller_reset_handler.start()
        
    
    def get_updated_ACEs(self, visitor_index_and_value):
        self._reset_timer()
        self._calculate_tie_lines(visitor_index_and_value)
        self._calculate_ACEs_from_LFC(visitor_index_and_value)
        return [self._ACE1_1, self._ACE2_1, self._ACE3_1]
    
    
    def _reset_controller_vars(self):
        self._vars_lock.acquire()
        self._ACE1_1 = 0.0
        self._ACE2_1 = 0.0
        self._ACE3_1 = 0.0
        self._integral1 = 0.0
        self._integral2 = 0.0
        self._integral3 = 0.0
        self._prev_time = 0.0
        self._tie_lines = [0.0, 0.0, 0.0]
        self._vars_lock.release()
    
    
    def _reset_controller_when_no_connection(self):
        max_disconnection_time = 5
        
        while(True):
            self._reset_timer()
            while(self._timer < max_disconnection_time):
                time.sleep(1)
                self._increment_timer()
            self._reset_controller_vars()
            _log.info(f"No connection for {max_disconnection_time} sec. LFC handler reset.")
 
    
    def _reset_timer(self):
        self._timer_lock.acquire()
        self._timer = 0
        self._timer_lock.release()
        
        
    def _increment_timer(self):
        self._timer_lock.acquire()
        self._timer += 1
        self._timer_lock.release()
    
    
    def _calculate_tie_lines(self, visitor_index_and_value):
        tl_13_T19 = visitor_index_and_value[10][1] # tie line from area 1 to 3, line number 19
        tl_12_T21 = visitor_index_and_value[11][1] # the rest by analogy
        tl_23_T05 = visitor_index_and_value[12][1] 
        tl_23_T02 = visitor_index_and_value[13][1] 
        tl_31_T19 = visitor_index_and_value[14][1]
        tl_21_T21 = visitor_index_and_value[15][1]
        tl_32_T05 = visitor_index_and_value[16][1]
        tl_32_T02 = visitor_index_and_value[17][1]
        
        self._tie_lines[0] = (tl_13_T19 + tl_12_T21 - 225.21686) / 100
        self._tie_lines[1] = (tl_21_T21 + tl_23_T02 + tl_23_T05 + 12.3572) / 100
        self._tie_lines[2] = (tl_31_T19 + tl_32_T02 + tl_32_T05 + 211.95215) / 100
        _log.info(f"TL 1: {self._tie_lines[0]} || TL 2: {self._tie_lines[1]} || TL 3: {self._tie_lines[2]}")
    
    
    def _calculate_ACEs_from_LFC(self, visitor_index_and_value):
        curr_time = time.time_ns()
        if self._prev_time == 0:
            self._set_prev_time(curr_time - 1)
        time_diff_in_sec = (curr_time - self._prev_time) / 1_000_000_000
        self._set_prev_time(curr_time)
        
        speed_6 = visitor_index_and_value[5][1] # for ACE1_1
        self._update_LFC_controller(1, speed_6, time_diff_in_sec)
        self._ACE1_1 = self._integral1 #0.02857
            
        speed_1 = visitor_index_and_value[0][1] # for ACE2_1
        self._update_LFC_controller(2, speed_1, time_diff_in_sec)
        self._ACE2_1 = self._integral2 #0.02574
        
        speed_3 = visitor_index_and_value[2][1] # for ACE3_1    
        self._update_LFC_controller(3, speed_3, time_diff_in_sec)
        self._ACE3_1 = self._integral3 #0.02371
        
        _log.info(f"Gen 1 | Speed: {speed_1} || Gen 3 | Speed: {speed_3} || Gen 6 | Speed: {speed_6}")
        _log.info(f"ACE1_1: {self._ACE1_1} || ACE2_1: {self._ACE2_1} || ACE3_1: {self._ACE3_1}")    
                
    
    def _set_prev_time(self, new_time):
        self._vars_lock.acquire()
        self._prev_time = new_time
        self._vars_lock.release()
        
        
    def _update_LFC_controller(self, area_num, freq, time_diff):
        error = (freq - self._base_rotor_speed) / self._base_rotor_speed * self._beta + self._tie_lines[area_num-1]
        new_value = error * -self._K_I * time_diff
        
        self._vars_lock.acquire()
        if area_num == 1:
            self._integral1 += new_value
        elif area_num == 2:
            self._integral2 += new_value
        elif area_num == 3:
            self._integral3 += new_value
        self._vars_lock.release()