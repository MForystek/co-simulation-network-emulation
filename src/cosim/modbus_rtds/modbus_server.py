from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusSlaveContext,
    ModbusServerContext
)
from pymodbus.server import StartAsyncTcpServer


class ModbusServer:
    def __init__(self, host: str, port: int, description=None,
                 co: ModbusSequentialDataBlock=None, di: ModbusSequentialDataBlock=None,
                 ir: ModbusSequentialDataBlock=None, hr: ModbusSequentialDataBlock=None):        
        self.host: str = host
        self.port: int = port
        self.description: str = description
        
        empty_registers_datablock = lambda : ModbusSequentialDataBlock(0x00, [0] * 100)
        empty_bits_datablock = lambda : ModbusSequentialDataBlock(0x00, [False] * 100)
        self.slave_context = ModbusSlaveContext(
            co=empty_bits_datablock() if co is None else co,      # Coils             (read/write): 00001 - 09999
            di=empty_bits_datablock() if di is None else di,      # Discrete inputs   (read):       10001 - 19999
            ir=empty_registers_datablock() if ir is None else ir, # Input registers   (read):       30001 - 39999
            hr=empty_registers_datablock() if hr is None else hr, # Holding registers (read/write): 40001 - 49999
        )
        self.context = ModbusServerContext(slaves=self.slave_context, single=True)
        self.sensor_server_coroutine = StartAsyncTcpServer(self.context, address=(self.host, self.port))
        
    
    def update_voltage(self, partial_float_voltages_in_pu: list, starting_address: int):
        # Update input registers with current float voltage value in pu
        self.slave_context.setValues(0x10, starting_address, partial_float_voltages_in_pu)
        
        
    def get_circuit_breaker_control_value(self):
        return self.slave_context.getValues(0x01, 0)[0]