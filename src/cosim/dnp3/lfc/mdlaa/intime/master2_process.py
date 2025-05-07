import numpy as np

from multiprocessing import Queue

from cosim.dnp3.master import MasterStation
from cosim.dnp3.lfc.mdlaa.secondary_MDLAA_handler import MDLAAHandlerSecondary
from cosim.dnp3.lfc.mdlaa.constants import step_time, NUM_ATTACKED_LOAD_BUSES


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