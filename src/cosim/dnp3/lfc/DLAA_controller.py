import logging
import time

from pydnp3.opendnp3 import GroupVariation

from cosim.dnp3.soe_handler import SOEHandlerAdjusted
from cosim.dnp3.lfc.LFC_master import MasterStation


class DLAASOEHandler(SOEHandlerAdjusted):
    def __init__(self, log_file_path="logs/soehandler.log", soehandler_log_level=logging.INFO, station_ref=None, *args, **kwargs):
        super().__init__(log_file_path, soehandler_log_level, station_ref, *args, **kwargs)
        self._NOMINAL_FREQ = 60 # HZ 
        
        self._load4_dlaa_coeff = 70
        self._load20_dlaa_coeff = 70
                
    
    def _process_incoming_data(self, info_gv, visitor_index_and_value):
        if info_gv in [GroupVariation.Group30Var6]:
            freq3 = visitor_index_and_value[2][1] / 1000
            freq_pu = (freq3 - self._NOMINAL_FREQ) / self._NOMINAL_FREQ
            self.logger.info(f"Freq: {freq3} Hz")
            load_4_dlaa = 1 + freq_pu * -self._load4_dlaa_coeff
            load_20_dlaa = 1 + freq_pu * -self._load20_dlaa_coeff
            self.logger.info(f"Load 4 DLAA: {load_4_dlaa} p.u.")
            self.logger.info(f"Load 20 DLAA: {load_20_dlaa} p.u.")
            self.station_ref.send_direct_point_command(40, 4, 7, load_4_dlaa)
            self.station_ref.send_direct_point_command(40, 4, 2, load_20_dlaa)
            

def main():
    logs_file = "logs/d_r_lfc_dlaa.log"
    outstation_ip2 = "172.24.14.213"
    port2 = 20002
    step_time = 100 # ms
    
    master = MasterStation(outstation_ip=outstation_ip2, port=port2, master_id=1, outstation_id=2, log_handler=None)
    soe_handler = DLAASOEHandler(logs_file, station_ref=master)
    master.configure_master(soe_handler, outstation_ip2, port2, scan_time=step_time)
    master.start()
    
    time.sleep(1_000_000_000)
    del master
    exit()
    

if __name__ == "__main__":
    main()