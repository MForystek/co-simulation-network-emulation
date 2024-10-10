import time
import threading
import pandas as pd
import pandapower as pp
import asyncio

from cosim import mylogging
from cosim.power_network import PowerNetwork
from cosim.modbus.modbus_server import ModbusServer


logger = mylogging.getLogger("pow_sim", "logs/pow_sim.log")


def increase_load_by(pnet: PowerNetwork, add_load, load_id) -> PowerNetwork:
    pnet.model.load.at[load_id, "p_mw"] = pnet.model.load.at[load_id, "p_mw"] + add_load
    return pnet


def simulate_step(pnet: PowerNetwork, voltage_sensor: ModbusServer, action, *args):
    # Do specified action
    if action is not None:
        pnet = action(pnet, *args)
    
    # Run powerflow
    pp.runpp(pnet.model)
    
    logger.info(pnet.get_values_for_printing())
    
    # Update Modbus voltage sensor
    # Using milli pu to avoid floats
    voltages_in_milli_pu = [int(voltage * 1000) for voltage in pnet.get_voltage_levels()]
    voltage_sensor.update_voltages(voltages_in_milli_pu)
    
    # Handle voltage level
    circuit_breaker_value = voltage_sensor.get_circuit_breaker_value()
    logger.info(f"Circuit breaker coil value: {circuit_breaker_value}")
    if circuit_breaker_value == True:
        pnet.open_switch()    
        
    
###################################################################


def main():
    pd.set_option('display.width', None)
    
    logger.info("--------------------------------------")
    logger.info("Setting up the power grid...")
    
    # Initializing power network
    pnet = PowerNetwork()
    
    # Activating Modbus voltage sensor
    voltage_sensor = ModbusServer("0.0.0.0", 5000, "Voltage sensor.")
    voltage_sensor_server = threading.Thread(target=asyncio.run,
                                             args=[voltage_sensor.sensor_server_coroutine],
                                             daemon=True)
    voltage_sensor_server.start()
    
    logger.info("Setup finished. Starting simulation...")
    logger.info("--------------------------------------")
        
    # Initial state
    simulate_step(pnet, voltage_sensor, None)
    
    # Simulate increasing load
    while True:
        simulate_step(pnet, voltage_sensor, increase_load_by, 0.2, 1)
        
        if not pnet.is_switch_closed(): 
            break
        time.sleep(0.1)
        
    
if __name__ == "__main__":
    main()