from cosim.utils import parse_arguments


args = parse_arguments()

if args.type in ["j", "json"]:
    from cosim.json.power import main as json_main
    json_main()
elif args.type in ["m", "modbus"]:
    from cosim.modbus.power import main as modbus_main
    modbus_main()
elif args.type in ["d", "dnp3"]:
    pass
elif args.type in ["c", "c37.118"]:
    pass
else:
    raise ValueError(f"Incorrect value of argument 'type': {args.type}")