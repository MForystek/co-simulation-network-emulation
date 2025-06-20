import sys
import asyncio
import threading

from pymodbus.client import AsyncModbusTcpClient
from pymodbus import ModbusException


from cosim import mylogging
from cosim.modbus.modbus_server import ModbusServer
from cosim.modbus.modbus_client import run_async_client    


MILLI = 1000

logger = mylogging.getLogger(__name__, "logs/m_pp_sensor.log")


async def forward_voltage_level_in_milli_pu(client: AsyncModbusTcpClient, modbus_server: ModbusServer):
    try:
        while True:
            # Read voltage values
            start_address = 0
            how_many = 2
            response = await client.read_holding_registers(start_address, how_many)
            if response.isError():
                logger.warning("Reading holding registers from sensor unsuccessful")
            if len(response.registers) != how_many:
                logger.warning(f"Read {len(response.registers)} registers, expected {how_many}")
            logger.info(f"Voltage 0: {response.registers[0]/MILLI:.3f}, Voltage 1: {response.registers[1]/MILLI:.3f}")
            
            # Update context with new voltage values
            modbus_server.update_voltage(response.registers, start_address)
            
            await asyncio.sleep(1)
    except ModbusException as e:
        pass
    
    
if __name__ == "__main__":
    if len(sys.argv) != 5:
        logger.error("Wrong number of arguments")
        exit(1)
        
    at_host = sys.argv[1]
    at_port = int(sys.argv[2])
    from_host = sys.argv[3]
    from_port = int(sys.argv[4])
        
    # Activating Modbus voltage sensor forwarder server
    voltage_sensor_forwarder = ModbusServer(at_host, at_port, "Voltage sensor forwarder.")
    voltage_sensor_server = threading.Thread(target=asyncio.run,
                                            args=[voltage_sensor_forwarder.sensor_server_coroutine],
                                            daemon=True)
    voltage_sensor_server.start()
    
    # Activiting Modbus voltage sensor forwarder client
    asyncio.run(run_async_client(from_host, from_port, logger=logger,
                                 modbus_calls=forward_voltage_level_in_milli_pu,
                                 modbus_server=voltage_sensor_forwarder),
                debug=True)
