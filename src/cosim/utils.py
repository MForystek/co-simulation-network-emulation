import argparse


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--type", required=True,
                        choices=["j", "json",
                                 "m", "modbus",
                                 "d", "dnp3",
                                 "c","c37.118"])
    return parser.parse_args()