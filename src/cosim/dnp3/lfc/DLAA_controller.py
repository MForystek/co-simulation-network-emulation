import logging
import time
import threading

from pydnp3.opendnp3 import GroupVariation

from cosim.dnp3.soe_handler import SOEHandlerAdjusted
from cosim.dnp3.lfc.LFC_master import MasterStation


class DLAASOEHandler(SOEHandlerAdjusted):
    def __init__(self, log_file_path="logs/soehandler.log", soehandler_log_level=logging.INFO, station_ref=None, *args, **kwargs):
        super().__init__(log_file_path, soehandler_log_level, station_ref, *args, **kwargs)
        self._LOAD4_NOMINAL_P = 500 # MW
        self._LOAD20_NOMINAL_P = 628 # MW
        self._NOMINAL_FREQ = 60 # HZ
        
        self._load4_dlaa_coeff = 90 # 75 without sensor's deadband
        self._load20_dlaa_coeff = 85 # 70 without sensor's deadband
    
    
    def _process_incoming_data(self, info_gv, visitor_index_and_value):
        if info_gv in [GroupVariation.Group30Var6]:
            freq3 = visitor_index_and_value[2][1]
            freq_pu = (freq3 - self._NOMINAL_FREQ) / self._NOMINAL_FREQ
            load_4_dlaa = freq_pu * -self._load4_dlaa_coeff * self._LOAD4_NOMINAL_P
            load_20_dlaa = freq_pu * -self._load20_dlaa_coeff * self._LOAD20_NOMINAL_P
            self.station_ref.send_direct_point_command(40, 4, 7, load_4_dlaa)
            self.station_ref.send_direct_point_command(40, 4, 2, load_20_dlaa)
            

def main():
    logs_file = "logs/d_r_lfc_dlaa.log"
    outstation_ip = "172.24.14.212"
    port = 20001
    
    master = MasterStation(outstation_ip=outstation_ip, port=port, master_id=1, outstation_id=2)
    soe_handler = DLAASOEHandler(logs_file, station_ref=master)
    master.configure_master(soe_handler, outstation_ip, port)
    
    master_thread = threading.Thread(target=master.start, daemon=True)
    master_thread.start()
    try:
        while True:
            time.sleep(1)
    finally:
        del master
        exit()


if __name__ == "__main__":
    main()