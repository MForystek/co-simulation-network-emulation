import logging

from pydnp3 import opendnp3, openpal, asiopal, asiodnp3
from pydnp3.opendnp3 import GroupVariation, GroupVariationID
from dnp3_python.dnp3station.visitors import *

from typing import Union, TypeVar

from cosim.mylogging import getLogger


_log = getLogger(__name__, "logs/master.py")

# alias
DbPointVal = Union[float, int, bool]

MasterCmdType = Union[opendnp3.AnalogOutputDouble64,
                      opendnp3.AnalogOutputFloat32,
                      opendnp3.AnalogOutputInt32,
                      opendnp3.AnalogOutputInt16,
                      opendnp3.ControlRelayOutputBlock]

OutstationCmdType = Union[opendnp3.Analog,
                          opendnp3.AnalogOutputStatus,
                          opendnp3.Binary,
                          opendnp3.BinaryOutputStatus]

MeasurementType = TypeVar("MeasurementType",
                          bound=opendnp3.Measurement)  # inheritance, e.g., opendnp3.Analog,


class DBHandler:
    """
        Work as an auxiliary database for outstation (Mimic SOEHAndler for master-station)
    """

    def __init__(self, stack_config=asiodnp3.OutstationStackConfig(opendnp3.DatabaseSizes.AllTypes(10)),
                 *args, **kwargs):

        self.stack_config = stack_config
        self._db: dict = self.config_db(stack_config)

        self.logger = getLogger(self.__class__.__name__, "logs/master.log", logging.INFO)
        
        
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
    def db(self) -> dict:
        return self._db

    def process(self, command, index):
        pass
        # _log.info(f"command {command}")
        # _log.info(f"index {index}")
        update_body: dict = {index: command.value}
        if self.db.get(command.__class__.__name__):
            self.db[command.__class__.__name__].update(update_body)
        else:
            self.db[command.__class__.__name__] = update_body
        # _log.info(f"========= self.db {self.db}")
        
        
class MyLogger(openpal.ILogHandler):
    def __init__(self):
        super(MyLogger, self).__init__()
        
    def Log(self, entry):
        filters = entry.filters.GetBitfield()
        location = entry.location.rsplit('/')[-1] if entry.location else ''
        message = entry.message
        _log.debug(f'Log\tfilters={filters}\tlocation={location}\tentry={message}')