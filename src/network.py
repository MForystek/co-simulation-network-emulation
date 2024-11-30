from cosim.utils import parse_arguments


args = parse_arguments()

if args.network in ["j", "json"]:
    if args.power in ["pp", "pandapower"]:
        from cosim.json.network import main as json_main
        json_main(args)
    else:
        raise ValueError(f"Supported power simulation for json network is PandaPower, wanted {args.power}.")
elif args.network in ["m", "modbus"]:
    if args.power in ["pp", "pandapower"]:
        from cosim.modbus.network import main as modbus_pandapower_main
        modbus_pandapower_main(args)
    elif args.power in ["r", "rtds"]:
        from cosim.modbus_rtds.network import main as modbus_rtds_main
        modbus_rtds_main(args)
elif args.network in ["d", "dnp3"]:
    pass
elif args.network in ["c", "c37.118"]:
    pass
else:
    raise ValueError(f"Incorrect value of argument 'type': {args.network}")