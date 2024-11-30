import argparse
import struct
import re


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--network", required=True,
                        choices=["j", "json",
                                 "m", "modbus",
                                 "d", "dnp3",
                                 "c","c37.118"],
                        help="Type of the network protocol used, or simple json messages.")
    parser.add_argument("-p", "--power", required=True,
                        choices=["pp", "pandapower",
                                 "r", "rtds"],
                        help="Type of the power simulator used.")
    parser.add_argument("-d", "--delay", required=False,
                        default="0ms", type=str,
                        help="Default 0ms. Delay imposed on the network connections in seconds or milliseconds. E.g. 0ms, 1s, 500ms")
    parser.add_argument("-b", "--bandwidth", required=False,
                        default="1", type=float,
                        help="Default 1Mb/s. Bandwidth of the network links relative to 1Mb/s. E.g. 0.1, 2.5")
    return parser.parse_args()
    

def check_correct_delay_format(value):
    if re.search("^0{1}m?s$|^[1-9]{1}\d*m?s$", value) is None:
        raise argparse.ArgumentTypeError(f"{value} is not a correct delay value.")
    return value


def convert_two_modbus_registers_into_float(upper_2_bytes_as_int: int, lower_2_bytes_as_int: int) -> float:
     upper_2_bytes = upper_2_bytes_as_int.to_bytes(2, 'big')
     lower_2_bytes = lower_2_bytes_as_int.to_bytes(2, 'big')
     float_bytes = upper_2_bytes + lower_2_bytes
     reconstructed_float = struct.unpack(">f", float_bytes)
     return reconstructed_float[0]
