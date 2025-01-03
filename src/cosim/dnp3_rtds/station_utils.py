import logging

from cosim import mylogging
from cosim.dnp3_pp.visitors import *

from pydnp3 import opendnp3, openpal, asiopal, asiodnp3
from pydnp3.opendnp3 import GroupVariation, GroupVariationID

from typing import Callable, Union, Dict, Tuple, List, Optional, Type, TypeVar

_log = mylogging.getLogger(__name__, "logs/master.py")

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

# TODO: add validating connection logic
# TODO: add validating configuration logic
#  (e.g., check if db at outstation side is configured correctly, i.e., OutstationStackConfig)


class AppChannelListener(asiodnp3.IChannelListener):
    """
        Override IChannelListener in this manner to implement application-specific channel behavior.
    """

    def __init__(self):
        super(AppChannelListener, self).__init__()

    def OnStateChange(self, state):
        _log.debug('In AppChannelListener.OnStateChange: state={}'.format(opendnp3.ChannelStateToString(state)))


def collection_callback(result=None):
    """
    :type result: opendnp3.CommandPointResult
    """
    print("Header: {0} | Index:  {1} | State:  {2} | Status: {3}".format(
        result.headerIndex,
        result.index,
        opendnp3.CommandPointStateToString(result.state),
        opendnp3.CommandStatusToString(result.status)
    ))


def command_callback(result: opendnp3.ICommandTaskResult = None):
    """
    :type result: opendnp3.ICommandTaskResult
    """
    # print("Received command result with summary: {}".format(opendnp3.TaskCompletionToString(result.summary)))
    # result.ForeachItem(collection_callback)
    pass


def restart_callback(result=opendnp3.RestartOperationResult()):
    if result.summary == opendnp3.TaskCompletion.SUCCESS:
        print("Restart success | Restart Time: {}".format(result.restartTime.GetMilliseconds()))
    else:
        print("Restart fail | Failure: {}".format(opendnp3.TaskCompletionToString(result.summary)))


def parsing_gvid_to_gvcls(gvid: GroupVariationID) -> GroupVariation:
    """Mapping gvId to GroupVariation member class

    :param opendnp3.GroupVariationID gvid: group-variance Id

    :return: GroupVariation member class.
    :rtype: opendnp3.GroupVariation

    :example:
    >>> parsing_gvid_to_gvcls(gvid=GroupVariationID(30, 6))
    GroupVariation.Group30Var6
    """
    # print("====gvId GroupVariationID", gvid)
    group: int = gvid.group
    variation: int = gvid.variation
    gv_cls: GroupVariation

    gv_cls = GroupVariationID(30, 6)  # default
    # auto parsing
    try:
        gv_cls = getattr(opendnp3.GroupVariation, f"Group{group}Var{variation}")
        assert gv_cls is not None
    except ValueError as e:
        _log.warning(f"Group{group}Var{variation} is not valid opendnp3.GroupVariation")

    return gv_cls


def parsing_gv_to_mastercmdtype(group: int, variation: int, val_to_set: DbPointVal) -> MasterCmdType:
    pass
    """
    hard-coded parsing, e.g., group40, variation:4 -> opendnp3.AnalogOutputDouble64
    """
    master_cmd: MasterCmdType
    # AnalogOutput
    if group == 40:
        if not type(val_to_set) in [float, int]:
            raise ValueError(f"val_to_set {val_to_set} of MasterCmdType group {group}, variation {variation} invalid.")
        if variation == 1:
            master_cmd = opendnp3.AnalogOutputInt32()
        elif variation == 2:
            master_cmd = opendnp3.AnalogOutputInt16()
        elif variation == 3:
            master_cmd = opendnp3.AnalogOutputFloat32()
        elif variation == 4:
            master_cmd = opendnp3.AnalogOutputDouble64()
        else:
            raise ValueError(f"val_to_set {val_to_set} of MasterCmdType group {group} invalid.")

        master_cmd.value = val_to_set
    # BinaryOutput
    elif group == 10 and variation in [1, 2]:
        master_cmd = opendnp3.ControlRelayOutputBlock()
        if not type(val_to_set) is bool:
            raise ValueError(f"val_to_set {val_to_set} of MasterCmdType group {group}, variation {variation} invalid.")
        if val_to_set is True:
            master_cmd.rawCode = 3
        else:
            master_cmd.rawCode = 4
    else:
        raise ValueError(f"val_to_set {val_to_set} of MasterCmdType group {group} invalid.")

    return master_cmd


# alias
# OutstationCmdType = Union[opendnp3.Analog, opendnp3.Binary, opendnp3.AnalogOutputStatus,
#                           opendnp3.BinaryOutputStatus]  # based on asiodnp3.UpdateBuilder.Update(**args)
# MasterCmdType = Union[opendnp3.AnalogOutputDouble64,
#                       opendnp3.AnalogOutputFloat32,
#                       opendnp3.AnalogOutputInt32,
#                       opendnp3.AnalogOutputInt16,
#                       opendnp3.ControlRelayOutputBlock]


def master_to_outstation_command_parser(master_cmd: MasterCmdType) -> OutstationCmdType:
    """
    Used to parse send command to update command, e.g., opendnp3.AnalogOutputDouble64 -> AnalogOutputStatus
    """
    # return None
    if type(master_cmd) in [opendnp3.AnalogOutputDouble64,
                            opendnp3.AnalogOutputFloat32,
                            opendnp3.AnalogOutputInt32,
                            opendnp3.AnalogOutputInt16]:
        return opendnp3.AnalogOutputStatus(value=master_cmd.value)
    elif type(master_cmd) is opendnp3.ControlRelayOutputBlock:
        # Note: ControlRelayOutputBlock requires to use hard-coded rawCode to retrieve value at this version.
        bi_value: bool
        if master_cmd.rawCode == 3:
            bi_value = True
        elif master_cmd.rawCode == 4:
            bi_value = False
        else:
            raise ValueError(
                f"master_cmd.rawCode {master_cmd.rawCode} is not a valid rawCode. (3: On/True, 4:Off/False.")
        return opendnp3.BinaryOutputStatus(value=bi_value)
    else:
        raise ValueError(f"master_cmd {master_cmd} with type {type(master_cmd)} is not a valid command.")


class DBHandler:
    """
        Work as an auxiliary database for outstation (Mimic SOEHAndler for master-station)
    """

    def __init__(self, stack_config=asiodnp3.OutstationStackConfig(opendnp3.DatabaseSizes.AllTypes(10)),
                 *args, **kwargs):

        self.stack_config = stack_config
        self._db: dict = self.config_db(stack_config)

        self.logger = mylogging.getLogger(self.__class__.__name__, "logs/master.log", logging.INFO)
        
        
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