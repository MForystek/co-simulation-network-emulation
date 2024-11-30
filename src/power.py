from cosim.utils import parse_arguments


args = parse_arguments()

if args.power not in ["pp", "pandapower"]:
    raise ValueError(f"Supported power simulation software is PandaPower, wanted {args.power}.")

if args.network in ["j", "json"]:
    from cosim.json.power import main as json_main
    json_main()
elif args.network in ["m", "modbus"]:
    from cosim.modbus.power import main as modbus_main
    modbus_main()
elif args.network in ["d", "dnp3"]:
    pass
elif args.network in ["c", "c37.118"]:
    pass
else:
    raise ValueError(f"Incorrect value of argument 'type': {args.network}")