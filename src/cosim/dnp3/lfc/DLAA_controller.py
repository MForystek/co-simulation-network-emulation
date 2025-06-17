import logging
import time

from pydnp3.opendnp3 import GroupVariation

from cosim.dnp3.soe_handler import SOEHandlerAdjusted
from cosim.dnp3.lfc.LFC_master import MasterStation


class DLAASOEHandler(SOEHandlerAdjusted):
    def __init__(self, log_file_path="logs/soehandler.log", soehandler_log_level=logging.INFO, station_ref=None, station_ref2=None, coeffs=[0]*18, *args, **kwargs):
        super().__init__(log_file_path, soehandler_log_level, station_ref, *args, **kwargs)
        self._station_ref2 = station_ref2
        self._NOMINAL_FREQ = 60 # HZ 
        self._coeffs = coeffs
                
    
    def _process_incoming_data(self, info_gv, visitor_index_and_value):
        if info_gv in [GroupVariation.Group30Var6]:
            freq3 = visitor_index_and_value[2][1] / 1000
            freq_pu = (freq3 - self._NOMINAL_FREQ) / self._NOMINAL_FREQ
            self.logger.info(f"Freq: {freq3} Hz")
            for i, coeff in enumerate(self._coeffs):
                if coeff == 0:
                    continue
                attack_load = 1 + freq_pu * -coeff
                self.logger.info(f"DLAA: {attack_load} p.u., coeff {coeff}")
                if i < 10:
                    self.station_ref.send_direct_point_command(40, 4, i, attack_load)
                else:
                    self._station_ref2.send_direct_point_command(40, 4, i, attack_load)
                

def main():
    logs_file = "logs/d_r_lfc_dlaa.log"
    outstation_ip = "172.24.14.212"
    port = 20001
    outstation_ip2 = "172.24.14.213"
    port2 = 20002
    step_time = 100 # ms
    
    coeffs = [0]*18
    coeffs[2] = 70
    coeffs[7] = 70
    
    master = MasterStation(outstation_ip=outstation_ip, port=port, master_id=1, outstation_id=2, log_handler=None)
    master2 = MasterStation(outstation_ip=outstation_ip2, port=port2, master_id=1, outstation_id=2, log_handler=None)
    soe_handler = DLAASOEHandler(logs_file, station_ref=master, station_ref2=master2, coeffs=coeffs)
    master.configure_master(soe_handler, outstation_ip, port, scan_time=step_time)
    master.start()
    master2.start()
    
    time.sleep(1_000_000_000)
    del master
    exit()
    

if __name__ == "__main__":
    main()