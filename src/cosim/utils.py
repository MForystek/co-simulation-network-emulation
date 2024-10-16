import argparse
import struct


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--network", required=True,
                        choices=["j", "json",
                                 "m", "modbus",
                                 "d", "dnp3",
                                 "c","c37.118"])
    parser.add_argument("-p", "--power", required=True,
                        choices=["pp", "pandapower",
                                 "r", "rtds"])
    return parser.parse_args()
    

def convert_two_modbus_registers_into_float(upper_2_bytes_as_int: int, lower_2_bytes_as_int: int) -> float:
     upper_2_bytes = upper_2_bytes_as_int.to_bytes(2, 'big')
     lower_2_bytes = lower_2_bytes_as_int.to_bytes(2, 'big')
     float_bytes = upper_2_bytes + lower_2_bytes
     reconstructed_float = struct.unpack(">f", float_bytes)
     return reconstructed_float[0]
