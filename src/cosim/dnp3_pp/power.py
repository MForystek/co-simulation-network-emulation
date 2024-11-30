import time
import threading
import pandas as pd
import pandapower as pp
import asyncio

from pydnp3 import opendnp3

from cosim import mylogging
from cosim.power_network import PowerNetwork
from cosim.dnp3_pp.outstation import OutstationApplication


logger = mylogging.getLogger("pow_sim", "logs/d_pp_pow_sim.log")


def increase_load_by(pnet: PowerNetwork, add_load, load_id) -> PowerNetwork:
    pnet.model.load.at[load_id, "p_mw"] = pnet.model.load.at[load_id, "p_mw"] + add_load
    return pnet


def simulate_step(pnet: PowerNetwork, voltage_sensor: OutstationApplication, action, *args):
    # Do specified action
    if action is not None:
        pnet = action(pnet, *args)
    
    # Run powerflow
    pp.runpp(pnet.model)
    
    logger.info(pnet.get_values_for_printing())
    
    # Update DNP3 voltage sensor
    # Using milli pu to avoid floats
    for i, voltage in enumerate(pnet.get_voltage_levels()):
        voltage_in_milli_pu = int(voltage * 1000)
        voltage_sensor.apply_update(opendnp3.Analog(voltage_in_milli_pu), i)
    
    # Handle voltage level
    circuit_breaker_value = voltage_sensor.get_from_db("Binary", 0)
    logger.info(f"Circuit breaker value: {circuit_breaker_value}")
    if circuit_breaker_value == True:
        pnet.open_switch()    
        
    
###################################################################


def main():
    pd.set_option('display.width', None)
    
    logger.info("--------------------------------------")
    logger.info("Setting up the power grid...")
    
    # Initializing power network
    pnet = PowerNetwork()
    
    # Activating DNP3 voltage sensor
    voltage_sensor = OutstationApplication("0.0.0.0", 20002)
    voltage_sensor_server = threading.Thread(target=voltage_sensor.enable(), daemon=True)
    voltage_sensor_server.start()
    
    logger.info("Setup finished. Starting simulation...")
    logger.info("--------------------------------------")
        
    # Initial state
    voltage_sensor.apply_update(opendnp3.Binary(False), 0)
    simulate_step(pnet, voltage_sensor, None)
    
    # Simulate increasing load
    while True:
        simulate_step(pnet, voltage_sensor, increase_load_by, 0.2, 1)
        
        if not pnet.is_switch_closed(): 
            break
        time.sleep(0.1)
    
    voltage_sensor.shutdown()
    exit()
        
    
if __name__ == "__main__":
    main()