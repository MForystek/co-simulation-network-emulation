import numpy as np
import logging

from pydnp3.opendnp3 import GroupVariation

from cosim.mylogging import getLogger
from cosim.dnp3.lfc.mdlaa.constants import NUM_LOAD_BUSES
from cosim.dnp3.soe_handler import SOEHandlerAdjusted


log = getLogger(__name__, "logs/MDLAA.log", logging.INFO)

# Secondary master station applying the calculated attacks to second set of loads
class MDLAAHandlerSecondary(SOEHandlerAdjusted):
    def __init__(self, log_file_path="logs/soehandler.log", soehandler_log_level=logging.INFO, station_ref=None, attack=np.zeros(NUM_LOAD_BUSES), *args, **kwargs):
        super().__init__(log_file_path, soehandler_log_level, station_ref, *args, **kwargs)
        
        # Constants
        self._NUM_OF_ATTACKED_LOADS = 8
        
        # MDLAA attack storage
        self._curr_attack = attack
        self._prev_attack = np.zeros(NUM_LOAD_BUSES)
        
        
    def _process_incoming_data(self, info_gv, visitor_ind_val):
        if info_gv in [GroupVariation.Group30Var6]:          
            if not (self._curr_attack == self._prev_attack).all():
                self._prev_attack = self._curr_attack.copy()
                self._do_attack()
                
    
    def _do_attack(self):
        loads = self._curr_attack[NUM_LOAD_BUSES - self._NUM_OF_ATTACKED_LOADS:]
        for i in range(self._NUM_OF_ATTACKED_LOADS):
            self.station_ref.send_direct_point_command(40, 4, i, float(loads[i]))
        log.debug(f"Doing DLAA2: {loads}")