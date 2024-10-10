from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusSlaveContext,
    ModbusServerContext
)
from pymodbus.server import StartAsyncTcpServer


class ModbusServer:
    def __init__(self, host: str, port: int, description=None):        
        self.host: str = host
        self.port: int = port
        self.description: str = description
        
        datablock = lambda : ModbusSequentialDataBlock(0x00, [0] * 100)
        self.slave_context = ModbusSlaveContext(
            co=datablock(), # Coils             (read/write): 00001 - 09999
            di=datablock(), # Discrete inputs   (read):       10001 - 19999
            ir=datablock(), # Input registers   (read):       30001 - 39999
            hr=datablock(), # Holding registers (read/write): 40001 - 49999
        )
        self.context = ModbusServerContext(slaves=self.slave_context, single=True)
        self.sensor_server_coroutine = StartAsyncTcpServer(self.context, address=(self.host, self.port))
        
    
    def update_voltages(self, voltages_in_milli_pu: list):
        # Update holding registers with current voltage values
        self.slave_context.setValues(0x10, 0, voltages_in_milli_pu)
        
        
    def get_circuit_breaker_value(self):
        return self.slave_context.getValues(0x01, 0)[0]