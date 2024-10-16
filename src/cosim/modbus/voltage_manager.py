import sys
import asyncio

from pymodbus.client import AsyncModbusTcpClient
from pymodbus import ModbusException

from cosim import mylogging
from cosim.modbus.modbus_client import run_async_client    


logger = mylogging.getLogger(__name__, "logs/manager.log")


async def read_voltage_level_in_milli_pu(client: AsyncModbusTcpClient, to_host, to_port):
    try:
        while True:
            start_address = 0
            how_many = 2
            response = await client.read_holding_registers(start_address, how_many)
            if response.isError():
                logger.warning("Reading holding registers from sensor unsuccessful")
            if len(response.registers) != how_many:
                logger.warning(f"Read {len(response.registers)} registers, expected {how_many}")
            logger.info(f"Voltage 0: {response.registers[0]/1000:.3f}, Voltage 1: {response.registers[1]/1000:.3f}")
            
            for i, register in enumerate(response.registers):
                if register < 950 and register != 0:
                    logger.info("**************************************")
                    logger.info(f"Voltage level too low at bus {i}: {register/1000:.3f} pu")
                    logger.info("Sending open circuit breaker command")
                    logger.info("**************************************")
                    await run_async_client(to_host, to_port, logger=logger,
                                           modbus_calls=send_open_circuit_breaker_signal)
                    return
            await asyncio.sleep(1)
    except ModbusException as e:
        pass
    

async def send_open_circuit_breaker_signal(client: AsyncModbusTcpClient):
    start_address = 0
    new_value = True
    response = await client.write_coil(start_address, new_value)
    if response.isError():
        logger.warning("Writing to actuator coil unsuccessful")
    if len(response.bits) != 8:
        logger.warning(f"Got {len(response.bits)} bits from actuator, expected {8}")
    

if __name__ == "__main__":
    if len(sys.argv) != 5:
        logger.error("Wrong number of arguments")
        exit(1)
        
    from_host = sys.argv[1]
    from_port = int(sys.argv[2])
    to_host = sys.argv[3]
    to_port = int(sys.argv[4])
    
    asyncio.run(run_async_client(from_host, from_port, logger=logger,
                                 modbus_calls=read_voltage_level_in_milli_pu,
                                 to_host=to_host, to_port=to_port),
                debug=True)