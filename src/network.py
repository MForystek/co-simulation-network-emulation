from cosim.utils import parse_arguments


args = parse_arguments()

# IEEE 39-bus system
if args.lfc:
    from cosim.dnp3.lfc.network import main as lfc_main
    lfc_main(args)
    exit()

# JSON
if args.network in ["j", "json"]:
    if args.power in ["pp", "pandapower"]:
        from cosim.json_pp.network import main as json_main
        json_main(args)
    else:
        raise ValueError(f"Supported power simulation for json network is PandaPower, wanted {args.power}.")
# MODBUS
elif args.network in ["m", "modbus"]:
    if args.power in ["pp", "pandapower"]:
        from cosim.modbus.pandapower.network import main as modbus_pandapower_main
        modbus_pandapower_main(args)
    elif args.power in ["r", "rtds"]:
        from cosim.modbus.rtds.network import main as modbus_rtds_main
        modbus_rtds_main(args)
# DNP3
elif args.network in ["d", "dnp3"]:
    if args.power in ["pp", "pandapower"]:
        from cosim.dnp3.pandapower.network import main as dnp3_pandapower_main
        dnp3_pandapower_main(args)
    elif args.power in ["r", "rtds"]:
        from cosim.dnp3.rtds.network import main as dnp3_rtds_main
        dnp3_rtds_main(args)
# C37.118
elif args.network in ["c", "c37.118"]:
    print("C37.118 network is not implemented yet.")
else:
    raise ValueError(f"Incorrect value of argument 'type': {args.network}")