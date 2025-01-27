import threading
import time

from pydnp3 import opendnp3, openpal, asiopal, asiodnp3

from cosim.dnp3.pandapower.station_utils import DBHandler, MyLogger
from cosim.mylogging import getLogger


LOG_LEVELS = opendnp3.levels.NORMAL | opendnp3.levels.ALL_COMMS

_log = getLogger(__name__, "logs/d_pp_outstation.log")


class OutstationApplication(opendnp3.IOutstationApplication):
    outstationApp = None
    
    def __init__(self, local_ip, port):
        super(OutstationApplication, self).__init__()
        self.stack_config = self.configure_stack()
        self.configure_database(self.stack_config.dbConfig)
        
        threads_to_allocate = 1
        self.log_handler = MyLogger()
        self.manager = asiodnp3.DNP3Manager(threads_to_allocate, self.log_handler)
        
        self.retry_parameters = asiopal.ChannelRetry().Default()
        self.listener = AppChannelListener()
        self.channel = self.manager.AddTCPServer("server",
                                                 LOG_LEVELS,
                                                 self.retry_parameters,
                                                 local_ip,
                                                 port,
                                                 self.listener)
        
        self.command_handler = OutstationCommandHandler()
        self.outstation = self.channel.AddOutstation("outstation",
                                                     self.command_handler,
                                                     self,
                                                     self.stack_config)

        self.db_handler = DBHandler(stack_config=self.stack_config)
        OutstationApplication.set_outstation_app(self)
        _log.info('Outstation initialization complete.')
    
        
    @staticmethod
    def configure_stack():
        # Value chosen empirically
        db_event_buffer_size = 10
        stack_config = asiodnp3.OutstationStackConfig(opendnp3.DatabaseSizes.AllTypes(db_event_buffer_size))
        stack_config.outstation.eventBufferConfig = opendnp3.EventBufferConfig().AllTypes(db_event_buffer_size)
        stack_config.outstation.params.allowUnsolicited = True
        stack_config.link.LocalAddr = 2
        stack_config.link.RemoteAddr = 1
        stack_config.link.KeepAliveTimeout = openpal.TimeDuration().Max()
        return stack_config
        
    @staticmethod
    def configure_database(db_config):
        # Voltage Bus 0
        db_config.analog[0].clazz = opendnp3.PointClass.Class2
        db_config.analog[0].svariation = opendnp3.StaticAnalogVariation.Group30Var1
        db_config.analog[0].evariation = opendnp3.EventAnalogVariation.Group32Var1
        # Voltage Bus 1
        db_config.analog[1].clazz = opendnp3.PointClass.Class2
        db_config.analog[1].svariation = opendnp3.StaticAnalogVariation.Group30Var1
        db_config.analog[1].evariation = opendnp3.EventAnalogVariation.Group32Var1
        # Circuit Breaker status
        db_config.binary[0].clazz = opendnp3.PointClass.Class2
        db_config.binary[0].svariation = opendnp3.StaticBinaryVariation.Group1Var2
        db_config.binary[0].evariation = opendnp3.EventBinaryVariation.Group2Var2
        
    @classmethod
    def get_outstation_app(cls):
        return cls.outstationApp
    
    @classmethod
    def set_outstation_app(cls, outstationApp):
        if cls.outstationApp is None:
            cls.outstationApp = outstationApp
    
    def get_from_db(self, type_name, index):
        return self.db_handler.db.get(type_name, [])[index]
    
    def enable(self):
        _log.info('Enabling the outstation. Now traffic starts to flow.')
        self.outstation.Enable()
    
    def shutdown(self):
        _log.info('Outstation exiting.')
        self.manager.Shutdown()
        
    # Overridden
    def ColdRestartSupport(self):
        return opendnp3.RestartMode.UNSUPPORTED
    
    # Overridden
    def GetApplicationIIN(self):
        application_iin = opendnp3.ApplicationIIN()
        application_iin.configCorrupt = False
        application_iin.deviceTrouble = False
        application_iin.localControl = False
        application_iin.needTime = False
        return application_iin
    
    # Overridden
    def SupportsAssignClass(self):
        return False
    
    # Overridden
    def SupportsWriteAbsoluteTime(self):
        return False
    
    # Overridden
    def SupportsWriteTimeAndInterval(self):
        return False
    
    # Overridden
    def WarmRestartSupport(self):
        return opendnp3.RestartMode.UNSUPPORTED
    
    @classmethod
    def process_point_value(cls, command_type, command, index, op_type):
        """
            A PointValue was received from the Master. Process its payload.

        :param command_type: (string) Either 'Select' or 'Operate'.
        :param command: A ControlRelayOutputBlock or else a wrapped data value (AnalogOutputInt16, etc.).
        :param index: (integer) DNP3 index of the payload's data definition.
        :param op_type: An OperateType, or None if command_type == 'Select'.
        """
        _log.info(f'Processing received point value for index {index}: {command}')
        if command_type == 'Operate' and type(command) == opendnp3.ControlRelayOutputBlock \
            and index == 0 and op_type == opendnp3.OperateType.DIRECT_OPERATE:
            if command.functionCode == opendnp3.ControlCode.LATCH_ON:
                cls.get_outstation_app().apply_update(opendnp3.Binary(0), 0)
                _log.info("CB closed")
            elif command.functionCode == opendnp3.ControlCode.LATCH_OFF:
                cls.get_outstation_app().apply_update(opendnp3.Binary(1), 0)
                _log.info("CB open")
                
        
    def apply_update(self, value, index):
        """
            Record an opendnp3 data value (Analog, Binary, etc.) in the outstation's database.

            The data value gets sent to the Master as a side-effect.

        :param value: An instance of Analog, Binary, or another opendnp3 data value.
        :param index: (integer) Index of the data definition in the opendnp3 database.
        """        
        _log.info(f'Recording {type(value).__name__} measurement, index={index}, value={value.value}')
        builder = asiodnp3.UpdateBuilder()
        builder.Update(value, index)
        update = builder.Build()
        OutstationApplication.get_outstation_app().outstation.Apply(update)
        self.db_handler.process(value, index)
        # _log.info(f"Success {self.get_from_db(type(value).__name__, index)}")


class AppChannelListener(asiodnp3.IChannelListener):
    def __init__(self):
        super(AppChannelListener, self).__init__()
        
    def OnStateChange(self, state):
        _log.debug(f'In AppChannelListener.OnStateChange: state={state}')
    

class OutstationCommandHandler(opendnp3.ICommandHandler):
    def Start(self):
        _log.debug('In OutstationCommandHandler.Start')
        
    def End(self):
        _log.debug('In OutstationCommandHandler.End')
        
    def Select(self, command, index):
        OutstationApplication.process_point_value('Select', command, index, None)
        return opendnp3.CommandStatus.SUCCESS
    
    def Operate(self, command, index, op_type):
        OutstationApplication.process_point_value('Operate', command, index, op_type)
        return opendnp3.CommandStatus.SUCCESS
    

def main():
    local_ip = "0.0.0.0"
    port = 20002
    app = OutstationApplication(local_ip, port)
    threading.Thread(None, app.enable(), daemon=True).start()
    time.sleep(300)
    #input("Press any key to exit...")
    app.shutdown()
    exit()


if __name__ == '__main__':
    main()