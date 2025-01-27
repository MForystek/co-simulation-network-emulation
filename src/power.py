from cosim.utils import parse_arguments


args = parse_arguments()

if args.power not in ["pp", "pandapower"]:
    raise ValueError(f"Supported power simulation software is PandaPower, wanted {args.power}.")

# JSON
if args.network in ["j", "json"]:
    from cosim.json_pp.power import main as json_main
    json_main()
# MODBUS
elif args.network in ["m", "modbus"]:
    from cosim.modbus.pandapower.power import main as modbus_main
    modbus_main()
# DNP3
elif args.network in ["d", "dnp3"]:
    from cosim.dnp3.pandapower.power import main as dnp3_main
    dnp3_main()
# C37.118
elif args.network in ["c", "c37.118"]:
    pass
else:
    raise ValueError(f"Incorrect value of argument 'type': {args.network}")