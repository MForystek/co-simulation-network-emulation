import logging
import threading
import time

from pydnp3 import opendnp3, asiodnp3, openpal, asiopal
from pydnp3.opendnp3 import GroupVariation
from dnp3_python.dnp3station.visitors import *

from cosim.dnp3.soe_handler import SOEHandlerAdjusted
from cosim.dnp3.master import MasterStation
from cosim.mylogging import getLogger

_log = getLogger(__name__, "logs/d_r_lfc_forwarder.log")

SCALING_TO_INT = 1000000

class MyLogger(openpal.ILogHandler):
    def __init__(self):
        super(MyLogger, self).__init__()
        
    def Log(self, entry):
        filters = entry.filters.GetBitfield()
        location = entry.location.rsplit('/')[-1] if entry.location else ''
        message = entry.message
        _log.debug(f'Log\tfilters={filters}\tlocation={location}\tentry={message}')


class ForwarderSOEHandler(SOEHandlerAdjusted):
    def __init__(self, log_file_path="logs/soehandler.log", soehandler_log_level=logging.INFO, station_ref=None, outstation_app=None, *args, **kwargs):
        super().__init__(log_file_path, soehandler_log_level, station_ref, *args, **kwargs)
        self.outstation_app: OutstationApplication = outstation_app
    
    def _process_incoming_data(self, info_gv, visitor_index_and_value):
        _log.debug(f'Processing incoming data for info_gv={info_gv}, visitor_index_and_value={visitor_index_and_value}')
        if info_gv in [GroupVariation.Group30Var6]:
            for index, value in visitor_index_and_value:
                analog_value = opendnp3.Analog(value*SCALING_TO_INT)
                self.outstation_app.apply_update(analog_value, index)
                _log.debug(f'Data forwarded to local outstation: index={index}, value={value}')


class OutstationApplication(opendnp3.IOutstationApplication):
    outstation = None
    
    def __init__(self, local_ip, port, local_addr, remote_addr, cmd_handler, initial_analogs):
        super(OutstationApplication, self).__init__()
        self.stack_config = self.configure_stack(local_addr, remote_addr)
        self.configure_database(self.stack_config.dbConfig)
        
        threads_to_allocate = 1
        self.log_handler = MyLogger()
        self.manager = asiodnp3.DNP3Manager(threads_to_allocate, self.log_handler)
        
        self.retry_parameters = asiopal.ChannelRetry().Default()
        self.listener = AppChannelListener()
        self.channel = self.manager.AddTCPServer("server",
                                                opendnp3.levels.NORMAL | opendnp3.levels.ALL_COMMS,
                                                self.retry_parameters,
                                                local_ip,
                                                port,
                                                self.listener)
        
        self.command_handler = cmd_handler
        self.outstation = self.channel.AddOutstation("outstation",
                                                    self.command_handler,
                                                    self,
                                                    self.stack_config)
        
        self.db_handler = DBHandler(stack_config=self.stack_config)

        if initial_analogs:
            self._load_initial_analog_values(initial_analogs)

        _log.info('Outstation initialization complete.')
    
    
    @staticmethod
    def configure_stack(local_addr, remote_addr):
        db_event_buffer_size = 22
        sizes = opendnp3.DatabaseSizes()
        sizes.numAnalog = 18
        sizes.numAnalogOutputStatus = 4
        stack_config = asiodnp3.OutstationStackConfig(sizes)
        stack_config.outstation.eventBufferConfig = opendnp3.EventBufferConfig().AllTypes(db_event_buffer_size)
        stack_config.outstation.params.allowUnsolicited = False
        stack_config.link.LocalAddr = local_addr
        stack_config.link.RemoteAddr = remote_addr
        stack_config.link.KeepAliveTimeout = openpal.TimeDuration().Max()
        return stack_config
        
    @staticmethod
    def configure_database(db_config):
        # Configure analog points for incoming data (Group30Var6)
        for i in range(18):
            db_config.analog[i].clazz = opendnp3.PointClass.Class2
            db_config.analog[i].svariation = opendnp3.StaticAnalogVariation.Group30Var6
            db_config.analog[i].evariation = opendnp3.EventAnalogVariation.Group32Var6
            db_config.analog[i].deadband = 0
        
        # Configure analog output points for outgoing commands (Group40Var4)
        for i in range(4): 
            db_config.aoStatus[i].clazz = opendnp3.PointClass.Class2
            db_config.aoStatus[i].svariation = opendnp3.StaticAnalogOutputStatusVariation.Group40Var4
            db_config.aoStatus[i].evariation = opendnp3.EventAnalogOutputStatusVariation.Group42Var4
            db_config.aoStatus[i].deadband = 0
    
    def enable(self):
        _log.info('Enabling the outstation.')
        self.outstation.Enable()
    
    def shutdown(self):
        _log.info('Outstation exiting.')
        self.manager.Shutdown()
    
    @classmethod
    def get_outstation(cls):
        if cls.outstation is None:
            raise RuntimeError("Outstation not initialized.")
        return cls.outstation
    
    @classmethod
    def set_outstation(cls, outstation):
        cls.outstation = outstation
        _log.info('Outstation set successfully.')
    
    @classmethod
    def process_point_value(cls, command_type, command, index, op_type):
        pass

    
    def apply_update(self, value, index):
        _log.debug(f'Recording {type(value).__name__} measurement, index={index}, value={value.value}')
        builder = asiodnp3.UpdateBuilder()
        # First update the static value
        builder.Update(value, index)
        # Then update the event buffer
        builder.Update(value, index, opendnp3.EventMode.Force)
        update = builder.Build()
        self.outstation.Apply(update)
        self.db_handler.process(value, index)
        _log.debug(f'Successfully recorded update for index={index}, value={value.value}')

    # Required IOutstationApplication methods
    def ColdRestartSupport(self):
        return opendnp3.RestartMode.UNSUPPORTED
    
    def GetApplicationIIN(self):
        """Return the application-controlled IIN field."""
        application_iin = opendnp3.ApplicationIIN()
        application_iin.configCorrupt = False
        application_iin.deviceTrouble = False
        application_iin.localControl = False
        application_iin.needTime = False
        iin_field = application_iin.ToIIN()
        _log.debug('OutstationApplication.GetApplicationIIN: IINField LSB={}, MSB={}'.format(iin_field.LSB,
                                                                                             iin_field.MSB))
        return application_iin
    
    def SupportsAssignClass(self):
        return False
    
    def SupportsWriteAbsoluteTime(self):
        return False
    
    def SupportsWriteTimeAndInterval(self):
        return False
    
    def WarmRestartSupport(self):
        return opendnp3.RestartMode.UNSUPPORTED

    def _load_initial_analog_values(self, values: list[float]):
        builder = asiodnp3.UpdateBuilder()
        for idx, val in enumerate(values):
            if idx >= self.stack_config.dbConfig.sizes.numAnalog:
                break  # ignore excess values
            builder.Update(opendnp3.Analog(val*SCALING_TO_INT), idx, opendnp3.EventMode.Suppress)
        self.outstation.Apply(builder.Build())
        _log.info(f'Loaded {min(len(values), self.stack_config.dbConfig.sizes.numAnalog)} initial analog values.')

class AppChannelListener(asiodnp3.IChannelListener):
    def __init__(self):
        super(AppChannelListener, self).__init__()
        
    def OnStateChange(self, state):
        _log.debug(f'In AppChannelListener.OnStateChange: state={state}')

class OutstationCommandHandler(opendnp3.ICommandHandler):
    def __init__(self, master_station=None):
        super(OutstationCommandHandler, self).__init__()
        self.master_station = master_station
        
    def Start(self):
        _log.debug('In OutstationCommandHandler.Start')
        
    def End(self):
        _log.debug('In OutstationCommandHandler.End')
        
    def Select(self, command, index):
        return opendnp3.CommandStatus.SUCCESS
    
    def Operate(self, command, index, op_type):
        _log.debug(f'{command.__class__.__name__} command received: index={index}, value={command.value}, op_type={op_type}')
        if self.master_station and isinstance(command, opendnp3.AnalogOutputDouble64):
            self.master_station.send_direct_point_command(40, 4, index, command.value)
        OutstationApplication.process_point_value('Operate', command, index, op_type)
        return opendnp3.CommandStatus.SUCCESS

class DBHandler:
    def __init__(self, stack_config):
        self.stack_config = stack_config
        self._db = self.config_db(stack_config)
        
    @staticmethod
    def config_db(stack_config):
        db = {}
        for number, gv_name in zip([stack_config.dbConfig.sizes.numBinary,
                                   stack_config.dbConfig.sizes.numBinaryOutputStatus,
                                   stack_config.dbConfig.sizes.numAnalog,
                                   stack_config.dbConfig.sizes.numAnalogOutputStatus],
                                  ["Analog", "AnalogOutputStatus",
                                   "Binary", "BinaryOutputStatus"]):
            val_body = dict((n, None) for n in range(number))
            db[gv_name] = val_body
        return db
    
    @property
    def db(self):
        return self._db
    
    def process(self, command, index):
        update_body = {index: command.value}
        if self.db.get(command.__class__.__name__):
            self.db[command.__class__.__name__].update(update_body)
            _log.debug(f'Updated database: {command.__class__.__name__}[{index}] = {command.value}')
        else:
            self.db[command.__class__.__name__] = update_body
            _log.debug(f'Created new database entry: {command.__class__.__name__}[{index}] = {command.value}')

def main():
    logs_file = "logs/d_r_lfc_forwarder.log"
    
    initial_analogs = [377, 377, 377, 377, 377, 377, 377, 377, 377, 377,
                       -4.77014, 229.987, 93.0968, 124.107, 4.79325, -229.561, -92.8474, -123.898]
    
    # External outstation connection details (where we get data from)
    external_outstation_ip = "172.24.14.211"
    external_outstation_port = 20000
    external_outstation_id = 2
    external_master_id = 1
    
    # Local outstation details (where LFC_master.py will connect to)
    local_outstation_ip = "0.0.0.0"
    local_outstation_port = 20003
    local_outstation_id = 4
    local_master_id = 3
    
    # Initialize master to connect to external outstation
    master = MasterStation(outstation_ip=external_outstation_ip, 
                          port=external_outstation_port, 
                          master_id=external_master_id,
                          outstation_id=external_outstation_id)
    
    # Initialize outstation with command handler that has reference to master
    handler = OutstationCommandHandler(master_station=master)
    outstation_app = OutstationApplication(local_outstation_ip,
                                           local_outstation_port,
                                           local_outstation_id,
                                           local_master_id,
                                           cmd_handler = handler,
                                           initial_analogs = initial_analogs)
    outstation_thread = threading.Thread(target=outstation_app.enable, daemon=True)
    outstation_thread.start()
    
    soe_handler = ForwarderSOEHandler(logs_file, 
                                      station_ref=master,
                                      outstation_app=outstation_app)
    master.configure_master(soe_handler, external_outstation_ip, external_outstation_port)
    
    # Start master thread
    master_thread = threading.Thread(target=master.start, daemon=True)
    master_thread.start()
    
    try:
        while True:
            time.sleep(1)
    finally:
        outstation_app.shutdown()
        del master
        exit()

if __name__ == '__main__':
    main()