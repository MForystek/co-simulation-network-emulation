import logging
import threading
import time

from pydnp3.opendnp3 import GroupVariation
from dnp3_python.dnp3station.visitors import *

from cosim.dnp3.lfc.LFCHandler import LFCHandler
from cosim.dnp3.soe_handler import SOEHandler
from cosim.dnp3.master import MasterStation


class IEEE39BusSOEHandler(SOEHandler):
    def __init__(self, log_file_path="logs/soehandler.log", soehandler_log_level=logging.INFO, station_ref=None, *args, **kwargs):
        super().__init__(log_file_path, soehandler_log_level, station_ref, *args, **kwargs)
        self._LFC_handler = LFCHandler()
    
    
    def _process_incoming_data(self, info_gv, visitor_index_and_value):
        if info_gv in [GroupVariation.Group30Var6]:            
            ACEs = self._LFC_handler.get_updated_ACEs(visitor_index_and_value)
            self.station_ref.send_direct_point_command(40, 4, 0, ACEs[0])
            self.station_ref.send_direct_point_command(40, 4, 1, ACEs[1])
            self.station_ref.send_direct_point_command(40, 4, 2, ACEs[2])

        
def main():
    logs_file = "logs/d_r_lfc_master.log"
    outstation_ip = "172.24.14.211"
    port = 20002
    
    master = MasterStation(outstation_ip=outstation_ip, port=port, master_id=1, outstation_id=2)
    soe_handler = IEEE39BusSOEHandler(logs_file, station_ref=master)
    master.configure_master(soe_handler, outstation_ip, port)
    
    master_thread = threading.Thread(target=master.start, daemon=True)
    master_thread.start()
    try:
        while True:
            time.sleep(1)
    finally:
        del master
        exit()

    
if __name__ == '__main__':
    main()