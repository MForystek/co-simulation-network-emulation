import time
import threading

from pydnp3.opendnp3 import GroupVariation

from cosim.dnp3.master import MasterStation
from cosim.dnp3.soe_handler import SOEHandlerAdjusted


class RSOEHandler(SOEHandlerAdjusted):    
    def _process_incoming_data(self, info_gv, visitor_ind_val):
        if info_gv in [GroupVariation.Group30Var6]:
            voltage_0 = visitor_ind_val[0][1] # p.u.
            voltage_1 = visitor_ind_val[1][1] # p.u.
            self.logger.info(f"Bus 0 | Voltage: {voltage_0} p.u. || Bus 1 | Voltage: {voltage_1} p.u.")
            if voltage_0 != 0 and voltage_1 != 0:
                if (voltage_0 < 0.95 or voltage_1 < 0.95) and self.db["Binary"][0] == False:
                    self.logger.warning("Voltage too low, opening circuit breaker!")
                    self.station_ref.send_direct_point_command(10, 1, 0, False)
                elif self.db["Binary"][0] == True and voltage_0 > 0.95 and voltage_1 > 0.95:
                    self.logger.info("Voltage in norm, closing circuit breaker.")
                    self.station_ref.send_direct_point_command(10, 1, 0, True)


def main():
    outstation_ip = "172.24.14.211"
    port = 20002
    logs_file = "logs/d_r_master.log"    
    
    master = MasterStation(outstation_ip=outstation_ip, port=port, master_id=1, outstation_id=2)
    soe_handler = RSOEHandler(logs_file, station_ref=master)
    master.configure_master(soe_handler, outstation_ip, port)
    
    threading.Thread(target=master.start(), daemon=True)
    try:
        while True:
            time.sleep(1)
    finally:
        del master
        exit()
    
    
if __name__ == "__main__":
    main()