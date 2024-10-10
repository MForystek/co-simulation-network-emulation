import asyncio

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException


async def run_async_client(host, port, logger, modbus_calls=None, **kwargs):
    while True:
        try:
            async with AsyncModbusTcpClient(host, port=port) as manager_client:
                await manager_client.connect()
                
                if manager_client.connected:
                    logger.info("Client connected")
                else:
                    logger.warning("Client cannot connect")
                    continue   
                
                if modbus_calls:
                    await modbus_calls(manager_client, **kwargs)
                break
        except ModbusException:
            pass
        finally:
            await asyncio.sleep(2)