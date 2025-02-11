import logging
import threading
import time

from pydnp3.opendnp3 import GroupVariation
from dnp3_python.dnp3station.visitors import *

from cosim.dnp3.soe_handler import SOEHandler
from cosim.dnp3.master import MasterStation


class LFCSOEHandler(SOEHandler):
    def __init__(self, log_file_path="logs/soehandler.log", soehandler_log_level=logging.INFO, station_ref=None, *args, **kwargs):
        super().__init__(log_file_path, soehandler_log_level, station_ref, *args, **kwargs)
        self._integral1 = 0.0
        self._integral2 = 0.0
        self._integral3 = 0.0
        self._ACE1 = 0.0
        self._ACE2 = 0.0
        self._ACE3 = 0.0
        self.prev_time = 0.0
    
    
    def _process_incoming_data(self, info_gv, visitor_ind_val):
        if info_gv in [GroupVariation.Group30Var6]:
            curr_time = time.time_ns()
            if self.prev_time == 0:
                self.prev_time = curr_time - 1
            time_diff_in_sec = (curr_time - self.prev_time) / 1_000_000_000
            self.prev_time = curr_time
            
            K_I = 0.005
            
            speed_1 = visitor_ind_val[0][1] # for ACE2_1
            speed_3 = visitor_ind_val[2][1] # for ACE3_1
            speed_6 = visitor_ind_val[5][1] # for ACE1_1
            
            tl_13_T19 = visitor_ind_val[10][1] # tie line from area 1 to 3, line number 19
            tl_12_T21 = visitor_ind_val[11][1] # the rest by analogy
            tl_23_T05 = visitor_ind_val[12][1] 
            tl_23_T02 = visitor_ind_val[13][1] 
            tl_31_T19 = visitor_ind_val[14][1]
            tl_21_T21 = visitor_ind_val[15][1]
            tl_32_T05 = visitor_ind_val[16][1]
            tl_32_T02 = visitor_ind_val[17][1]
            
            tl1 = (tl_13_T19 + tl_12_T21 - 143.442) / 100
            tl2 = (tl_21_T21 + tl_23_T02 + tl_23_T05 - 247.21) / 100
            tl3 = (tl_31_T19 + tl_32_T02 + tl_32_T05 + 389.5655) / 100
            
            self.logger.info(f"Gen 1 | Speed: {speed_1} || Gen 3 | Speed: {speed_3} || Gen 6 | Speed: {speed_6}")
            self.logger.info(f"TL 1: {tl1} || TL 2: {tl2} || TL 3: {tl3}")
            
            self._update_controller(1, speed_6, tl1, K_I, time_diff_in_sec)
            ACE1_1 = self._integral1 + 0.02857 #0.02957
            
            self._update_controller(2, speed_1, tl2, K_I, time_diff_in_sec)
            ACE2_1 = self._integral2 + 0.02574 #0.02974
            
            self._update_controller(3, speed_3, tl3, K_I, time_diff_in_sec)
            ACE3_1 = self._integral3 + 0.02371 #0.01971
            
            self.logger.info(f"ACE1_1: {ACE1_1} || ACE2_1: {ACE2_1} || ACE3_1: {ACE3_1}")
            
            self.station_ref.send_direct_point_command(40, 4, 0, ACE1_1)
            self.station_ref.send_direct_point_command(40, 4, 1, ACE2_1)
            self.station_ref.send_direct_point_command(40, 4, 2, ACE3_1)
        

    def _update_controller(self, area_num, freq, tie_lines, K_I, time_diff):
        base_rotor_speed = 377
        beta = 20
        
        error = (freq - base_rotor_speed) / base_rotor_speed * beta + tie_lines
        update_integral = error * -K_I * time_diff
        if area_num == 1:
            self._integral1 += update_integral
        elif area_num == 2:
            self._integral2 += update_integral
        elif area_num == 3:
            self._integral3 += update_integral
     
        
def main():
    logs_file = "logs/d_r_lfc_master.log"
    outstation_ip = "172.24.14.211"
    port = 20002
    
    master = MasterStation(outstation_ip=outstation_ip, port=port, master_id=1, outstation_id=2)
    soe_handler = LFCSOEHandler(logs_file, station_ref=master)
    master.configure_master(soe_handler, outstation_ip, port)
    
    threading.Thread(target=master.start(), daemon=True)
    try:
        while True:
            time.sleep(1)
    finally:
        del master
        exit()

    
if __name__ == '__main__':
    main()