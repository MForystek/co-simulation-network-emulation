import sys
import asyncio
import threading

from pymodbus.datastore import ModbusSequentialDataBlock
from pymodbus.client import AsyncModbusTcpClient
from pymodbus import ModbusException

from cosim import mylogging
from cosim.modbus_rtds.modbus_server import ModbusServer
from cosim.modbus_rtds.modbus_client import run_async_client    


logger = mylogging.getLogger(__name__, "logs/actuator.log")


async def forward_circuit_breaker_command(client: AsyncModbusTcpClient, modbus_server: ModbusServer):
    try:
        while True:
            # Check circuit breaker status coil
            circuit_breaker_value = modbus_server.get_circuit_breaker_control_value()
            logger.info(f"Circuit breaker coil value: {circuit_breaker_value}")
            await control_circuit_breaker(client, circuit_breaker_value, start_address=0)
            await asyncio.sleep(1)
    except ModbusException as e:
        pass
   
   
async def control_circuit_breaker(client: AsyncModbusTcpClient, circuit_breaker_value: bool,
                                  start_address: int):
    if circuit_breaker_value:
        logger.info("Opening circuit breaker")
    else:
        logger.info("Closing circuit breaker")
        
    new_value = not circuit_breaker_value
    response = await client.write_coil(start_address, new_value)
    if response.isError():
        logger.warning("Writing to coil unsuccessful")
    if len(response.bits) != 8:
        logger.warning(f"Got {len(response.bits)} bits, expected {8}")        
     
    
if __name__ == "__main__":
    if len(sys.argv) != 5:
        logger.error("Wrong number of arguments")
        exit(1)
        
    at_host = sys.argv[1]
    at_port = int(sys.argv[2])
    from_host = sys.argv[3]
    from_port = int(sys.argv[4])
        
    # Activating Modbus voltage sensor forwarder server
    voltage_sensor_forwarder = ModbusServer(at_host, at_port, "Voltage sensor forwarder.",
                                            co=ModbusSequentialDataBlock(0x00, [0]*100))
    voltage_sensor_server = threading.Thread(target=asyncio.run,
                                            args=[voltage_sensor_forwarder.sensor_server_coroutine],
                                            daemon=True)
    voltage_sensor_server.start()
    
    # Activiting Modbus voltage sensor forwarder client
    asyncio.run(run_async_client(from_host, from_port, logger=logger,
                                 modbus_calls=forward_circuit_breaker_command,
                                 modbus_server=voltage_sensor_forwarder),
                debug=True)
