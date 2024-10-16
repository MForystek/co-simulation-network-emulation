import sys
import asyncio
import threading

from pymodbus.client import AsyncModbusTcpClient
from pymodbus import ModbusException


from cosim import mylogging
from cosim.utils import convert_two_modbus_registers_into_float
from cosim.modbus_rtds.modbus_server import ModbusServer
from cosim.modbus_rtds.modbus_client import run_async_client    


logger = mylogging.getLogger(__name__, "logs/sensor.log")


async def forward_voltage_level_in_pu(client: AsyncModbusTcpClient, modbus_server: ModbusServer, bus_number: int):
    try:
        while True:
            # Read voltage values
            start_address = 0
            how_many = 2
            response = await client.read_input_registers(start_address, how_many)
            if response.isError():
                logger.warning("Reading input registers from sensor unsuccessful")
            if len(response.registers) != how_many:
                logger.warning(f"Read {len(response.registers)} registers, expected {how_many}")
            
            # Concate two registers into float
            v_rms = convert_two_modbus_registers_into_float(response.registers[0], response.registers[1])
            logger.info(f"Voltage rms at Bus {bus_number}: {v_rms:.3f}")
            
            # Update context with new voltage value
            modbus_server.update_voltage(response.registers, bus_number * 2)
            
            await asyncio.sleep(1)
    except ModbusException as e:
        pass
     
    
if __name__ == "__main__":
    if  len(sys.argv) >= 5 and (len(sys.argv) + 1) % 2 != 0:
        logger.error("Wrong number of arguments")
        exit(1)
    
    at_host = sys.argv[1]
    at_port = int(sys.argv[2])
    
    from_hosts = []
    from_ports = []
    for i in range(3, len(sys.argv), 2):
        from_hosts.append(sys.argv[i])
        from_ports.append(int(sys.argv[i+1]))
        
    # Activating Modbus voltage sensor forwarder server
    voltage_sensor_forwarder = ModbusServer(at_host, at_port, "Voltage sensor forwarder.")
    voltage_sensor_server = threading.Thread(target=asyncio.run,
                                            args=[voltage_sensor_forwarder.sensor_server_coroutine],
                                            daemon=True)
    voltage_sensor_server.start()
    
    
    # Activiting Modbus voltage sensor forwarder client for all but the last one buses
    for i in range(len(from_hosts)-1):
        voltage_sensor_instance = threading.Thread(target=asyncio.run,
                                                args=[run_async_client(from_hosts[i], from_ports[i], logger=logger,
                                                                        modbus_calls=forward_voltage_level_in_pu,
                                                                        modbus_server=voltage_sensor_forwarder,
                                                                        bus_number=i)],
                                                daemon=True)
        voltage_sensor_instance.start()
        
    # Activiting Modbus voltage sensor forwarder client for the last bus
    asyncio.run(run_async_client(from_hosts[-1], from_ports[-1], logger=logger,
                                 modbus_calls=forward_voltage_level_in_pu,
                                 modbus_server=voltage_sensor_forwarder,
                                 bus_number=len(from_hosts)-1),
                debug=True)

