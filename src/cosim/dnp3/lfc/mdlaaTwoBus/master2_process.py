import numpy as np
import logging

from multiprocessing import Queue

from pydnp3.opendnp3 import GroupVariation

from cosim.dnp3.master import MasterStation
from cosim.dnp3.soe_handler import SOEHandlerAdjusted
from cosim.dnp3.lfc.mdlaaTwoBus.constants import step_time, NUM_ATTACKED_LOAD_BUSES, NUM_OF_LOADS_SECONDARY_HANDLER


class MDLAAHandlerSecondary(SOEHandlerAdjusted):
    def __init__(self, log_file_path="logs/soehandler.log", soehandler_log_level=logging.INFO, station_ref=None, attack=np.zeros(NUM_ATTACKED_LOAD_BUSES), *args, **kwargs):
        super().__init__(log_file_path, soehandler_log_level, station_ref, *args, **kwargs)
        
        # MDLAA attack storage
        self._curr_attack = attack
        self._prev_attack = np.ones(NUM_ATTACKED_LOAD_BUSES)
        
        
    def _process_incoming_data(self, info_gv, visitor_ind_val):
        if info_gv in [GroupVariation.Group30Var6]:          
            if not (self._curr_attack == self._prev_attack).all():
                self._prev_attack = self._curr_attack.copy()
                self._do_attack()
                
    
    def _do_attack(self):
        loads = self._curr_attack[NUM_ATTACKED_LOAD_BUSES - NUM_OF_LOADS_SECONDARY_HANDLER:]
        for i in range(NUM_OF_LOADS_SECONDARY_HANDLER):
            self.station_ref.send_direct_point_command(40, 4, i, float(loads[i]))


def master2_process(main_to_master2: Queue):
    logs_file = "logs/d_r_lfc_mdlaa.log"
    outstation_ip2 = "172.24.14.213"
    port2 = 20002
    
    loads_coeffs = np.ones(NUM_ATTACKED_LOAD_BUSES, dtype=np.float32)
    
    master2 = MasterStation(outstation_ip=outstation_ip2, port=port2, master_id=1, outstation_id=2, log_handler=None)
    soe_handler2 = MDLAAHandlerSecondary(logs_file, station_ref=master2, attack=loads_coeffs)
    master2.configure_master(soe_handler2, outstation_ip2, port2, scan_time=step_time)
    master2.start()
    
    while True:
        data = main_to_master2.get()
        if type(data) == int and data == -1:
            exit(0)
        
        for i in range(len(data)):
            loads_coeffs[i] = data[i]