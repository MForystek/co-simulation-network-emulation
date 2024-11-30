import json
import time
import socket
import socketserver
import threading
import pandas as pd
import pandapower as pp

from cosim import mylogging
from cosim.power_network import PowerNetwork


logger = mylogging.getLogger("pow_sim", "logs/j_pp_pow_sim.log")


def increase_load_by(net, add_load) -> PowerNetwork:
    net.load.at[1, "p_mw"] = net.load.at[1, "p_mw"] + add_load
    return net


def simulate_step(net: PowerNetwork, data_collector_addr, action, *args):
    if action is not None:
        net.model = action(net.model, *args)
    pp.runpp(net.model)
    logger.info(net.get_values_for_printing())
    
    voltage_data = net.get_values_for_sending()
    send_voltage_data(data_collector_addr, voltage_data)


def send_voltage_data(srv_addr, voltage_data):
    with socket.create_connection(srv_addr) as client:
        client.sendall(bytes(json.dumps(voltage_data), "utf-8"))
        

def get_voltage_level_handler(net):
    class VoltageLevelHandler(socketserver.BaseRequestHandler):
        def handle(self):
            voltage_data = json.loads(self.request.recv(1024).strip().decode('utf-8'))
            
            if voltage_data["vm_pu"] < 0.95 and net.is_switch_closed():
                net.open_switch()
                
                logger.info("**************************************")
                logger.info(f"Voltage level too low! {voltage_data['vm_pu']:.4f} pu")
                logger.info(f"Activating circuit breaker at {voltage_data['timestamp']}.")
                logger.info("**************************************")
    return VoltageLevelHandler


def handle_voltage_level(srv_addr, net):
    with socketserver.TCPServer(srv_addr, get_voltage_level_handler(net)) as server:
        server.serve_forever()
        

###################################################################


def main():
    pd.set_option('display.width', None)
    
    logger.info("--------------------------------------")
    logger.info("Setting up the power grid...")
    
    net = PowerNetwork()

    logger.info("Setup finished. Starting simulation...")
    logger.info("--------------------------------------")
    
    data_collector_addr = ("172.17.0.2", 2137)
    voltage_level_handler_addr = ("172.17.0.1", 3721)
    
    # Activating voltage level handler
    voltage_level_handling = threading.Thread(target=handle_voltage_level, 
                                              args=[voltage_level_handler_addr, net],
                                              daemon=True)
    voltage_level_handling.start()
        
    # Initial state
    simulate_step(net, data_collector_addr, None)
    
    while True:
        simulate_step(net, data_collector_addr, increase_load_by, 2)
            
        if not net.is_switch_closed():
            break
        time.sleep(0.5)
        

if __name__ == "__main__":
    main()