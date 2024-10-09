import time
import datetime
import pandapower as pp

class PowerNetwork:
    def __init__(self):        
        self.model = pp.create_empty_network()
        self._define_power_network()
        

    def _define_power_network(self):
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
        time.sleep(0.5)
        self.model.switch.at[0, "closed"] = False
        
    
    def get_values_for_printing(self) -> str:        
        voltage_levels = ""
        loads_levels = ""
        for i in range(self.model.res_bus.shape[0]):
            voltage_levels += f"| Bus {i}: {self.model.res_bus.at[i, 'vm_pu']:.3f} "
        for i in range(self.model.res_load.shape[0]):
            loads_levels += f"| Load {i}: {self.model.res_load.at[i, 'p_mw']:.3f} "
        return f"|| Vm [pu] {voltage_levels} || Power [MW] {loads_levels} ||"
    
    
    def get_values_for_sending(self) -> dict:
        timestamp = datetime.datetime.now()
        voltage_level = self.model.res_bus.at[1, "vm_pu"]
        return {"timestamp": str(timestamp), "vm_pu": voltage_level}
    
    
    def get_voltage_levels(self) -> list:
        return self.model.res_bus["vm_pu"].tolist()