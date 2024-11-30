from cosim.utils import parse_arguments


args = parse_arguments()

if args.power not in ["pp", "pandapower"]:
    raise ValueError(f"Supported power simulation software is PandaPower, wanted {args.power}.")

if args.network in ["j", "json"]:
    from cosim.json_pp.power import main as json_main
    json_main()
elif args.network in ["m", "modbus"]:
    from cosim.modbus_pp.power import main as modbus_main
    modbus_main()
elif args.network in ["d", "dnp3"]:
    from cosim.dnp3_pp.power import main as dnp3_main
    dnp3_main()
elif args.network in ["c", "c37.118"]:
    pass
else:
    raise ValueError(f"Incorrect value of argument 'type': {args.network}")