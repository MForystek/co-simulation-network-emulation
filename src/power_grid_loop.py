import json
import time
import datetime
import socket
import socketserver
import threading
import pandas as pd
import pandapower as pp

class PowerNetwork:
    def __init__(self, res_file_name: str):
        self.res_file_name = res_file_name
        self.model = pp.create_empty_network()
        self.clear_file()
        self.res_file = open(res_file_name, "a")


    def __del__(self):
        self.res_file.close()
        

    def define_power_network(self):
        bus0 = pp.create_bus(self.model, vn_kv=20, name="Bus 1")
        bus1 = pp.create_bus(self.model, vn_kv=20, name="Bus 2")

        gen0 = pp.create_gen(self.model, bus0, p_mw=10, vm_pu=1, name="Gen 1", slack=True)
        
        sgen0 = pp.create_sgen(self.model, bus1, p_mw=10, q_mvar=5, name="Gen 2")

        load0 = pp.create_load(self.model, bus0, p_mw=10, q_mvar=5, name="Load 1")
        load1 = pp.create_load(self.model, bus1, p_mw=10, q_mvar=5, name="Load 2")

        line0to1 = pp.create_line(self.model, from_bus=bus0, to_bus=bus1, length_km=1, std_type="NAYY 4x50 SE", name="Line 1 to 2")

        switch0 = pp.create_switch(self.model, bus1, element=line0to1, et="l", type="CB", closed=True)
        

    def is_switch_closed(self):
        return self.model.switch.at[0, "closed"]


    def open_switch(self):
        self.model.switch.at[0, "closed"] = False
        
    
    def get_values_for_printing(self) -> str:        
        timestamp = datetime.datetime.now()
        voltage_levels = ""
        loads_levels = ""
        for i in range(self.model.res_bus.shape[0]):
            voltage_levels += f"| Bus {i}: {self.model.res_bus.at[i, "vm_pu"]:.4f} "
        for i in range(self.model.res_load.shape[0]):
            loads_levels += f"| Load {i}: {self.model.res_load.at[i, "p_mw"]:} "
        return str(timestamp) + " || Vm [pu] " + voltage_levels + " || Power [MW] " + loads_levels + " ||"
    
    
    def get_values_for_sending(self) -> dict:
        timestamp = datetime.datetime.now()
        voltage_level = self.model.res_bus.at[1, "vm_pu"]
        return {"timestamp": str(timestamp), "vm_pu": voltage_level}
    
    
    def clear_file(self):
        with open(self.res_file_name, "w"):
            pass

        
def print_to_console_and_file(file, text):
    file.write(text + "\n")
    print(text)


def increase_load_by(net, add_load) -> PowerNetwork:
    net.load.at[1, "p_mw"] = net.load.at[1, "p_mw"] + add_load
    return net


def simulate_step(net: PowerNetwork, action, *args):
    if action is not None:
        net.model = action(net.model, *args)
    pp.runpp(net.model)


def get_voltage_level_handler(net):
    class VoltageLevelHandler(socketserver.BaseRequestHandler):
        def handle(self):
            voltage_data = json.loads(self.request.recv(1024).strip().decode('utf-8'))
            
            if voltage_data["vm_pu"] < 0.95 and net.is_switch_closed():
                net.open_switch()
                
                print("**************************************")
                print(f"Voltage level too low! {voltage_data["vm_pu"]:.4f} pu")
                print(f"Activating circuit breaker at {voltage_data["timestamp"]}.")
                print("**************************************")
    
    return VoltageLevelHandler


def handle_voltage_level(srv_addr, net):
    with socketserver.TCPServer(srv_addr, get_voltage_level_handler(net)) as server:
        server.serve_forever()
            

def send_voltage_data(srv_addr, voltage_data):
    with socket.create_connection(srv_addr) as client:
        client.sendall(bytes(json.dumps(voltage_data), "utf-8"))
        

###################################################################


if __name__ == "__main__":
    pd.set_option('display.width', None)
    
    print("--------------------------------------")
    print("Setting up the power grid...")
    print("--------------------------------------\n")
    
    net = PowerNetwork("res.txt")
    net.clear_file()
    net.define_power_network()
    
    print("--------------------------------------")
    print("Setup finished. Starting simulation...")
    print("--------------------------------------")
    
    data_collector_addr = ("172.17.0.2", 2137)
    voltage_level_handler_addr = ("172.17.0.1", 3721)
    
    # Activating voltage level handler
    voltage_level_handling = threading.Thread(target=handle_voltage_level, 
                                              args=[voltage_level_handler_addr, net],
                                              daemon=True)
    voltage_level_handling.start()
        
    # Initial state
    simulate_step(net, None)
    values = net.get_values_for_printing()
    print_to_console_and_file(net.res_file, values)
    
    voltage_data = net.get_values_for_sending()
    send_voltage_data(data_collector_addr, voltage_data)
    
    while True:
        simulate_step(net, increase_load_by, 2)
        
        # Printing to console and file
        values = net.get_values_for_printing()
        print_to_console_and_file(net.res_file, values)
        
        # Sending data over the network
        voltage_data = net.get_values_for_sending()
        send_voltage_data(data_collector_addr, voltage_data)
            
        if not net.model.switch.at[0, "closed"]:
            break
        time.sleep(0.5)