import datetime
import logging
import time

from typing import Callable, Dict, List, Optional, Tuple, Union

from pydnp3 import opendnp3
from pydnp3.opendnp3 import GroupVariation

from cosim.mylogging import getLogger
from cosim.lfc.visitors import *

# Aliases
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


class SOEHandler(opendnp3.ISOEHandler):
    """
        Override ISOEHandler in this manner to implement application-specific sequence-of-events behavior.

        This is an interface for SequenceOfEvents (SOE) callbacks from the Master stack to the application layer.
    """

    def __init__(self, soehandler_log_level=logging.INFO, station_ref=None, *args, **kwargs):
        super(SOEHandler, self).__init__()

        self.station_ref = station_ref

        # auxiliary database
        self._gv_index_value_nested_dict: Dict[GroupVariation, Optional[Dict[int, DbPointVal]]] = {}
        self._gv_ts_ind_val_dict: Dict[GroupVariation, Tuple[datetime.datetime, Optional[Dict[int, DbPointVal]]]] = {}
        self._gv_last_poll_dict: Dict[GroupVariation, Optional[datetime.datetime]] = {}

        # logging
        self.logger = getLogger(self.__class__.__name__, "logs/d_pp_master.log", soehandler_log_level)

        # db
        self._db = self.init_db()
        
        self._visitor_class_types: dict = {
            opendnp3.ICollectionIndexedBinary: VisitorIndexedBinary,
            opendnp3.ICollectionIndexedDoubleBitBinary: VisitorIndexedDoubleBitBinary,
            opendnp3.ICollectionIndexedCounter: VisitorIndexedCounter,
            opendnp3.ICollectionIndexedFrozenCounter: VisitorIndexedFrozenCounter,
            opendnp3.ICollectionIndexedAnalog: VisitorIndexedAnalog,
            opendnp3.ICollectionIndexedBinaryOutputStatus: VisitorIndexedBinaryOutputStatus,
            opendnp3.ICollectionIndexedAnalogOutputStatus: VisitorIndexedAnalogOutputStatus,
            opendnp3.ICollectionIndexedTimeAndInterval: VisitorIndexedTimeAndInterval
        }
        self._visitor_indexed_analog_ints: list = [
            # GroupVariation.Group30Var0,
            GroupVariation.Group30Var1,
            GroupVariation.Group30Var2,
            GroupVariation.Group30Var3,
            GroupVariation.Group30Var4,
            # GroupVariation.Group32Var0,
            GroupVariation.Group32Var1,
            GroupVariation.Group32Var2,
            GroupVariation.Group32Var3,
            GroupVariation.Group32Var4
        ]
        self._visitor_indexed_analog_output_status_ints: list = [
            # GroupVariation.Group40Var0,
            GroupVariation.Group40Var1,
            GroupVariation.Group40Var2,
            # GroupVariation.Group42Var0,
            GroupVariation.Group42Var1,
            GroupVariation.Group42Var2,
            GroupVariation.Group42Var3,
            GroupVariation.Group42Var4
        ]
        
        self._proportional1 = 0.0
        self._proportional2 = 0.0
        self._proportional3 = 0.0
        self._integral1 = 0.0
        self._integral2 = 0.0
        self._integral3 = 0.0
        self._ACE1 = 0.0
        self._ACE2 = 0.0
        self._ACE3 = 0.0
        # ACE liczone w stałych odstępach czasu 0.1 w osobnej pętli zamiast po wywołaniu SOEHandlera
        self.prev_time = 0.0

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
        visitor_class: Union[Callable, VisitorClass] = self._visitor_class_types[type(values)]
        visitor = visitor_class()  # init
        
        # hot-fix VisitorXXAnalog do not distinguish float and integer.
        # Parsing to Int
        if visitor_class == VisitorIndexedAnalog and info.gv in self._visitor_indexed_analog_ints:
            visitor = VisitorIndexedAnalogInt()
        elif visitor_class == VisitorIndexedAnalogOutputStatus and info.gv in self._visitor_indexed_analog_output_status_ints:
            visitor = VisitorIndexedAnalogOutputStatusInt()
        
        # Note: mystery method, magic side effect to update visitor.index_and_value
        values.Foreach(visitor)

        # visitor.index_and_value: List[Tuple[int, DbPointVal]]
        for index, value in visitor.index_and_value:
            log_string = 'SOEHandler.Process {0}\theaderIndex={1}\tdata_type={2}\tindex={3}\tvalue={4}'
            self.logger.debug(log_string.format(info.gv, info.headerIndex, type(values).__name__, index, value))
        
        info_gv: GroupVariation = info.gv    
        visitor_ind_val: List[Tuple[int, DbPointVal]] = visitor.index_and_value

        self._process_RTDS_data(info_gv, visitor_ind_val)

        self.logger.debug("======== SOEHandler.Process")
        self.logger.debug(f"info_gv {info_gv}")
        self.logger.debug(f"visitor_ind_val {visitor_ind_val}")
        self._post_process(info_gv=info_gv, visitor_ind_val=visitor_ind_val)


    def _process_RTDS_data(self, info_gv: GroupVariation, visitor_ind_val: List[Tuple[int, DbPointVal]]):
        if info_gv in [GroupVariation.Group30Var6]:
            speed_1 = visitor_ind_val[0][1] # for ACE2_1
            speed_3 = visitor_ind_val[2][1] # for ACE3_1
            speed_6 = visitor_ind_val[5][1] # for ACE1_1
            tl1 = visitor_ind_val[10][1]
            tl2 = visitor_ind_val[11][1]
            tl3 = visitor_ind_val[12][1]
            self.logger.info(f"Gen 1 | Speed: {speed_1} || Gen 3 | Speed: {speed_3} || Gen 6 | Speed: {speed_6}")
            self.logger.info(f"TL 1: {tl1} || TL 2: {tl2} || TL 3: {tl3}")
            
            curr_time = time.time_ns()
            if self.prev_time == 0:
                self.prev_time = curr_time - 1
            time_diff_in_sec = (curr_time - self.prev_time) / 1_000_000_000
            self.prev_time = curr_time
            
            K_I = 0.005
            K_P = 0.01
            
            self._update_controller(1, speed_6, tl1, K_P, K_I, time_diff_in_sec)
            ACE1_1 = self._integral1 + 0.02857
            
            self._update_controller(2, speed_1, tl2, K_P, K_I, time_diff_in_sec)
            ACE2_1 = self._integral2 + 0.02574
            
            self._update_controller(3, speed_3, tl3, K_P, K_I, time_diff_in_sec)
            ACE3_1 = self._integral3 + 0.02371
            
            self.logger.info(f"ACE1_1: {ACE1_1} || ACE2_1: {ACE2_1} || ACE3_1: {ACE3_1}")
            
            self.station_ref.send_direct_point_command(40, 4, 0, ACE1_1)
            self.station_ref.send_direct_point_command(40, 4, 1, ACE2_1)
            self.station_ref.send_direct_point_command(40, 4, 2, ACE3_1)
        

    def _update_controller(self, area_num, freq, tie_lines, K_P, K_I, time_diff):
        base_rotor_speed = 377
        beta = 20
        
        error = (freq - base_rotor_speed) / base_rotor_speed * beta + tie_lines
        update_integral = error * -K_I * time_diff
        if area_num == 1:
            #self._proportional1 = error * K_P
            self._integral1 += update_integral
        elif area_num == 2:
            #self._proportional2 = error * K_P
            self._integral2 += update_integral
        elif area_num == 3:
            #self._proportional3 = error * K_P
            self._integral3 += update_integral
            

    def _post_process(self, info_gv: GroupVariation, visitor_ind_val: List[Tuple[int, DbPointVal]]):
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
    def gv_index_value_nested_dict(self) -> Dict[GroupVariation, Optional[Dict[int, DbPointVal]]]:
        return self._gv_index_value_nested_dict

    @property
    def gv_ts_ind_val_dict(self):
        return self._gv_ts_ind_val_dict

    @property
    def gv_last_poll_dict(self) -> Dict[GroupVariation, Optional[datetime.datetime]]:
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
        _db = {"Analog": self._gv_index_value_nested_dict.get(GroupVariation.Group30Var1)}
        if _db.get("Analog"):
            self._db.update(_db)
        # for Binary
        _db = {"Binary": self._gv_index_value_nested_dict.get(GroupVariation.Group1Var2)}
        if _db.get("Binary"):
            self._db.update(_db)
        # for Binary
        _db = {"BinaryOutputStatus": self._gv_index_value_nested_dict.get(GroupVariation.Group10Var2)}
        if _db.get("BinaryOutputStatus"):
            self._db.update(_db)      
        # for AnalogDouble
        _db = {"AnalogDouble": self._gv_index_value_nested_dict.get(GroupVariation.Group30Var6)}
        if _db.get("AnalogDouble"):
            self._db.update(_db)
        # for AnalogDoubleOutputStatus
        _db = {"AnalogDoubleOutputStatus": self._gv_index_value_nested_dict.get(GroupVariation.Group40Var4)}
        if _db.get("AnalogDoubleOutputStatus"):
            self._db.update(_db)