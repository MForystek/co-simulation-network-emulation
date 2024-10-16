import sys
import asyncio

from pymodbus.client import AsyncModbusTcpClient
from pymodbus import ModbusException

from cosim import mylogging
from cosim.utils import convert_two_modbus_registers_into_float
from cosim.modbus_rtds.modbus_client import run_async_client    


logger = mylogging.getLogger(__name__, "logs/manager.log")


async def read_voltage_level_in_pu(client: AsyncModbusTcpClient, to_host, to_port):
    try:
        while True:
            start_address = 0
            how_many = 4
            response = await client.read_holding_registers(start_address, how_many)
            if response.isError():
                logger.warning("Reading input registers from sensor unsuccessful")
            if len(response.registers) != how_many:
                logger.warning(f"Read {len(response.registers)} registers, expected {how_many}")
            
            # Concate pairs of registers into floats
            v_rmss = []
            for i in range(0, how_many, 2):
                v_rmss.append(convert_two_modbus_registers_into_float(response.registers[i], response.registers[i+1]))
            logger.info(f"Voltage 0: {v_rmss[0]:.3f}, Voltage 1: {v_rmss[1]:.3f}")
            
            is_voltage_acceptable = True
            for i, v_rms in enumerate(v_rmss):
                if v_rms < 0.99:
                    is_voltage_acceptable = False
                if v_rms < 0.95 and v_rms != 0:
                    logger.warning("**************************************")
                    logger.warning(f"Voltage level too low at bus {i}: {v_rms:.3f} pu")
                    logger.warning("Sending open circuit breaker command")
                    logger.warning("**************************************")
                    await run_async_client(to_host, to_port, logger=logger,
                                           modbus_calls=send_control_circuit_breaker_signal,
                                           new_value=True)
            if is_voltage_acceptable:
                logger.info("Voltage levels acceptable, circuit breaker closed")
                await run_async_client(to_host, to_port, logger=logger,
                                       modbus_calls=send_control_circuit_breaker_signal,
                                       new_value=False)
            await asyncio.sleep(1)
    except ModbusException as e:
        pass
    

async def send_control_circuit_breaker_signal(client: AsyncModbusTcpClient, new_value: bool):
    start_address = 0
    response = await client.write_coil(start_address, new_value)
    logger.info(response)
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
                                 modbus_calls=read_voltage_level_in_pu,
                                 to_host=to_host, to_port=to_port),
                debug=True)
