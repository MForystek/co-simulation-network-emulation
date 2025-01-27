import datetime
import logging

from typing import Callable, Dict, List, Optional, Tuple, Union

from pydnp3 import opendnp3
from dnp3_python.dnp3station.visitors import *

from cosim.mylogging import getLogger

DbPointVal = Union[float, int, bool, None]
ICollectionIndexedVal = Union[opendnp3.ICollectionIndexedAnalog,
                              opendnp3.ICollectionIndexedBinary,
                              opendnp3.ICollectionIndexedAnalogOutputStatus,
                              opendnp3.ICollectionIndexedBinaryOutputStatus]
VisitorClass = Union[VisitorIndexedTimeAndInterval,
                     VisitorIndexedAnalog,
                     VisitorIndexedBinary,
                     VisitorIndexedCounter,
                     VisitorIndexedFrozenCounter,
                     VisitorIndexedAnalogOutputStatus,
                     VisitorIndexedBinaryOutputStatus,
                     VisitorIndexedDoubleBitBinary]
VisitorClassTypes: dict = {
    opendnp3.ICollectionIndexedBinary: VisitorIndexedBinary,
    opendnp3.ICollectionIndexedDoubleBitBinary: VisitorIndexedDoubleBitBinary,
    opendnp3.ICollectionIndexedCounter: VisitorIndexedCounter,
    opendnp3.ICollectionIndexedFrozenCounter: VisitorIndexedFrozenCounter,
    opendnp3.ICollectionIndexedAnalog: VisitorIndexedAnalog,
    opendnp3.ICollectionIndexedBinaryOutputStatus: VisitorIndexedBinaryOutputStatus,
    opendnp3.ICollectionIndexedAnalogOutputStatus: VisitorIndexedAnalogOutputStatus,
    opendnp3.ICollectionIndexedTimeAndInterval: VisitorIndexedTimeAndInterval
}
VisitorIndexedAnalogInts: list = [
    # GroupVariation.Group30Var0,
    opendnp3.GroupVariation.Group30Var1,
    opendnp3.GroupVariation.Group30Var2,
    opendnp3.GroupVariation.Group30Var3,
    opendnp3.GroupVariation.Group30Var4,
    # GroupVariation.Group32Var0,
    opendnp3.GroupVariation.Group32Var1,
    opendnp3.GroupVariation.Group32Var2,
    opendnp3.GroupVariation.Group32Var3,
    opendnp3.GroupVariation.Group32Var4
]
VisitorIndexedAnalogOutputStatusInts: list = [
    # GroupVariation.Group40Var0,
    opendnp3.GroupVariation.Group40Var1,
    opendnp3.GroupVariation.Group40Var2,
    # GroupVariation.Group42Var0,
    opendnp3.GroupVariation.Group42Var1,
    opendnp3.GroupVariation.Group42Var2,
    opendnp3.GroupVariation.Group42Var3,
    opendnp3.GroupVariation.Group42Var4
]


class SOEHandler(opendnp3.ISOEHandler):
    """
        Override ISOEHandler in this manner to implement application-specific sequence-of-events behavior.

        This is an interface for SequenceOfEvents (SOE) callbacks from the Master stack to the application layer.
    """

    def __init__(self, log_file_path="logs/soehandler.log", soehandler_log_level=logging.INFO, station_ref=None, *args, **kwargs):
        super(SOEHandler, self).__init__()

        self.station_ref = station_ref

        # auxiliary database
        self._gv_index_value_nested_dict: Dict[opendnp3.GroupVariation, Optional[Dict[int, DbPointVal]]] = {}
        self._gv_ts_ind_val_dict: Dict[opendnp3.GroupVariation, Tuple[datetime.datetime, Optional[Dict[int, DbPointVal]]]] = {}
        self._gv_last_poll_dict: Dict[opendnp3.GroupVariation, Optional[datetime.datetime]] = {}

        # logging
        self.logger = getLogger(self.__class__.__name__, log_file_path, soehandler_log_level)

        # db
        self._db = self.init_db()

    def Process(self, info,
                values: ICollectionIndexedVal,
                *args, **kwargs):
        """
            Process measurement data.
            Note: will only evoke when there is response from outstation

        :param info: HeaderInfo
        :param values: A collection of values received from the Outstation (various data types are possible).
        """
        # print("=========Process, info.gv, values", info.gv, values)
        visitor_class: Union[Callable, VisitorClass] = VisitorClassTypes[type(values)]
        visitor = visitor_class()  # init
        
        # hot-fix VisitorXXAnalog do not distinguish float and integer.
        # Parsing to Int
        if visitor_class == VisitorIndexedAnalog and info.gv in VisitorIndexedAnalogInts:
            visitor = VisitorIndexedAnalogInt()
        elif visitor_class == VisitorIndexedAnalogOutputStatus and info.gv in VisitorIndexedAnalogOutputStatusInts:
            visitor = VisitorIndexedAnalogOutputStatusInt()
        
        # Note: mystery method, magic side effect to update visitor.index_and_value
        values.Foreach(visitor)

        # visitor.index_and_value: List[Tuple[int, DbPointVal]]
        for index, value in visitor.index_and_value:
            log_string = 'SOEHandler.Process {0}\theaderIndex={1}\tdata_type={2}\tindex={3}\tvalue={4}'
            self.logger.debug(log_string.format(info.gv, info.headerIndex, type(values).__name__, index, value))
        
        info_gv: opendnp3.GroupVariation = info.gv    
        visitor_ind_val: List[Tuple[int, DbPointVal]] = visitor.index_and_value

        self.logger.debug("======== SOEHandler.Process")
        self.logger.debug(f"info_gv {info_gv}")
        self.logger.debug(f"visitor_ind_val {visitor_ind_val}")

        self._process_incoming_data(info_gv, visitor_ind_val)
        self._post_process(info_gv=info_gv, visitor_ind_val=visitor_ind_val)


    def _process_incoming_data(self, info_gv: opendnp3.GroupVariation, visitor_ind_val: List[Tuple[int, DbPointVal]]):
        pass            

    def _post_process(self, info_gv: opendnp3.GroupVariation, visitor_ind_val: List[Tuple[int, DbPointVal]]):
        """
        SOEHandler post process logic to stage data at MasterStation side
        to improve performance: e.g., consistent output

        info_gv: GroupVariation,
        visitor_ind_val: List[Tuple[int, DbPointVal]]
        """
        # Use dict update method to mitigate delay due to asynchronous communication. (i.e., return None)
        # Also, capture unsolicited updated values.
        if not self._gv_index_value_nested_dict.get(info_gv):
            self._gv_index_value_nested_dict[info_gv] = (dict(visitor_ind_val))
        else:
            self._gv_index_value_nested_dict[info_gv].update(dict(visitor_ind_val))

        # Use another layer of storage to handle timestamp related logic
        self._gv_ts_ind_val_dict[info_gv] = (datetime.datetime.now(),
                                             self._gv_index_value_nested_dict.get(info_gv))
        # Use another layer of storage to handle timestamp related logic
        self._gv_last_poll_dict[info_gv] = datetime.datetime.now()

    def Start(self):
        self.logger.debug('In SOEHandler.Start====')

    def End(self):
        self.logger.debug('In SOEHandler.End')

    @property
    def gv_index_value_nested_dict(self) -> Dict[opendnp3.GroupVariation, Optional[Dict[int, DbPointVal]]]:
        return self._gv_index_value_nested_dict

    @property
    def gv_ts_ind_val_dict(self):
        return self._gv_ts_ind_val_dict

    @property
    def gv_last_poll_dict(self) -> Dict[opendnp3.GroupVariation, Optional[datetime.datetime]]:
        return self._gv_last_poll_dict

    @property
    def db(self) -> dict:
        """micmic DbHandler.db"""
        self._consolidate_db()
        return self._db

    @staticmethod
    def init_db(size=10):
        db = {}
        for number, gv_name in zip([size, size, size, size, size],
                                   ["Analog", "AnalogOutputStatus",
                                    "Binary", "BinaryOutputStatus",
                                    "AnalogDouble"]):
            val_body = dict((n, None) for n in range(number))
            db[gv_name] = val_body

        return db

    def _consolidate_db(self):
        """map group variance to db with 4 keys:
        "Binary", "BinaryOutputStatus", "Analog", "AnalogOutputStatus"
        """
        pass
        # for Analog
        _db = {"Analog": self._gv_index_value_nested_dict.get(opendnp3.GroupVariation.Group30Var1)}
        if _db.get("Analog"):
            self._db.update(_db)
        # for AnalogOutputStatus
        _db = {"AnalogOutputStatus": self._gv_index_value_nested_dict.get(opendnp3.GroupVariation.Group40Var4)}
        if _db.get("AnalogOutputStatus"):
            self._db.update(_db)
        # for AnalogDouble
        _db = {"AnalogDouble": self._gv_index_value_nested_dict.get(opendnp3.GroupVariation.Group30Var6)}
        if _db.get("AnalogDouble"):
            self._db.update(_db)
        # for Binary
        _db = {"Binary": self._gv_index_value_nested_dict.get(opendnp3.GroupVariation.Group1Var2)}
        if _db.get("Binary"):
            self._db.update(_db)
        # for Binary
        _db = {"BinaryOutputStatus": self._gv_index_value_nested_dict.get(opendnp3.GroupVariation.Group10Var2)}
        if _db.get("BinaryOutputStatus"):
            self._db.update(_db)