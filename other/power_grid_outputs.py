import pandas as pd
import pandapower as pp
import matplotlib.pyplot as plt

from pandapower.plotting import simple_plotly, pf_res_plotly

class PowerNetwork:
    def __init__(self, res_file_name: str):
        self.res_file_name = res_file_name
        self.model = pp.create_empty_network()


    def define_network(self):
        bus0 = pp.create_bus(self.model, vn_kv=20, name="Bus 1")
        bus1 = pp.create_bus(self.model, vn_kv=20, name="Bus 2")

        gen0 = pp.create_gen(self.model, bus0, p_mw=10, vm_pu=1, name="Gen 1", slack=True)
        
        sgen0 = pp.create_sgen(self.model, bus1, p_mw=10, q_mvar=5, name="Gen 2")

        load0 = pp.create_load(self.model, bus0, p_mw=10, q_mvar=5, name="Load 1")
        load1 = pp.create_load(self.model, bus1, p_mw=10, q_mvar=5, name="Load 2")

        line0to1 = pp.create_line(self.model, from_bus=bus0, to_bus=bus1, length_km=1, std_type="NAYY 4x50 SE", name="Line 1 to 2")

        switch0 = pp.create_switch(self.model, bus1, element=line0to1, et="l", type="CB", closed=True)


    def simulate_step(self, action, *args):
        if action is not None:
            self.model = action(self.model, *args)
        pp.runpp(self.model)
        self.print_results()
        

    def open_switch(self):
        self.model.switch.at[0, "closed"] = False
    
    
    def clear_file(self):
        with open(self.res_file_name, "w"):
            pass


    def print_results(self):
        with open(self.res_file_name, "a") as file:
            # print_to_console_and_file(file, self.net.res_gen, "Generators")
            # print_to_console_and_file(file, self.net.res_sgen, "Static generators")
            # print_to_console_and_file(file, self.net.res_load, "Loads")
            print_to_console_and_file(file, self.model.res_line, "Lines")
            print_to_console_and_file(file, self.model.res_bus, "BUSES")
        


def print_to_console_and_file(file, dataFrame, name):
    file.write(name + "\n")
    file.write(str(dataFrame)+"\n\n")
    print(name)
    print(dataFrame)


def increase_load_by(net, add_load):
    net.load.at[1, "p_mw"] = net.load.at[1, "p_mw"] + add_load
    return net



if __name__ == "__main__":
    pd.set_option('display.width', None)
    
    net = PowerNetwork("res.txt")
    net.clear_file()
    net.define_network()
    
    # Initial state
    net.simulate_step(None)
    
    voltages_pu = net.model.res_bus["vm_pu"]
    buses_real_power = net.model.res_bus["p_mw"]
    loads_real_power = net.model.res_load["p_mw"]
    
    for i in range(10):
        net.simulate_step(increase_load_by, 5)
        voltages_pu = pd.concat([voltages_pu, net.model.res_bus["vm_pu"]], axis=1, ignore_index=True)
        buses_real_power = pd.concat([buses_real_power, net.model.res_bus["p_mw"]], axis=1, ignore_index=True)
        loads_real_power = pd.concat([loads_real_power, net.model.res_load["p_mw"]], axis=1, ignore_index=True)
        
        # Open circuit breaker if voltage level too low
        if net.model.res_bus.at[1, "vm_pu"] < 0.95:
            net.open_switch()
    
    
    voltages_pu = voltages_pu.transpose().fillna(0)
    buses_real_power = buses_real_power.transpose().fillna(0)
    loads_real_power = loads_real_power.transpose().fillna(0)
    
    
    # Plotting
    if (0):
        plt.subplot(1,3,1)
        plt.plot(voltages_pu)
        plt.axhline(0.95, color="r", linestyle=":")
        plt.grid()
        plt.title("Votage in pu (Buses)")
        plt.legend(["Bus 0", "Bus 1"])
        
        plt.subplot(1,3,2)
        plt.plot(buses_real_power)
        plt.grid()
        plt.title("Power in MW (Buses)")
        plt.legend(["Bus 0", "Bus 1"])
        
        plt.subplot(1,3,3)
        plt.plot(loads_real_power)
        plt.grid()
        plt.title("Power in MW (Loads)")
        plt.legend(["Load 0", "Load 1"])
        
        plt.show()
