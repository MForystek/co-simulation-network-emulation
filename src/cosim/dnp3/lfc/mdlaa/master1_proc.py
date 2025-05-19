import logging

from multiprocessing import Queue

from pydnp3.opendnp3 import GroupVariation

from cosim.dnp3.master import MasterStation
from cosim.dnp3.soe_handler import SOEHandlerAdjusted


class SOEHandlerMaster1(SOEHandlerAdjusted):
    def __init__(self, station_ref, master1_to_main:Queue, log_file_path="logs/d_r_lfc_mdlaa.log", soehandler_log_level=logging.INFO, *args, **kwargs):
        super().__init__(log_file_path, soehandler_log_level, station_ref, *args, **kwargs)
        self.master1_to_main = master1_to_main
        
    
    def _process_incoming_data(self, info_gv, visitor_index_and_value):
        if info_gv in [GroupVariation.Group30Var6]:
            self.master1_to_main.put(visitor_index_and_value)
        

def master1_process(main_to_master1: Queue, master1_to_main: Queue, step_time):
    outstation_ip = "172.24.14.212"
    port = 20001

    master1 = MasterStation(outstation_ip=outstation_ip, port=port, master_id=1, outstation_id=2, log_handler=None)
    soe_handler = SOEHandlerMaster1(station_ref=master1, master1_to_main=master1_to_main)
    master1.configure_master(soe_handler, outstation_ip, port, scan_time=step_time)
    master1.start()

    while True:
        data = main_to_master1.get()
        if type(data) == int and data == -1:
            master1_to_main.put(-1)
            exit(0)
            
        master1.send_direct_point_command(data[0], data[1], data[2], data[3])
