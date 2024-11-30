import pathlib

from mininet.net import Containernet
from mininet.node import OVSSwitch
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel


def main(args):
    if args is None:
        delay = "0ms"
        bandwidth = 1.0
    else:
        delay = args.delay
        bandwidth = args.bandwidth
    
    setLogLevel('info')

    net = Containernet() 

    code_dir = str(pathlib.Path(__file__).parent.parent.parent.resolve())
    volume_dir = code_dir + ":/app"

    # Hosts
    sensor = net.addDocker("sensor", ip="192.168.0.1/24", dimage="modbusnet:latest",
                            ports=[5001], port_bindings={5001:5001},
                            volumes=[volume_dir])
    manager = net.addDocker("manager", ip="192.168.0.2/24",dimage="modbusnet:latest",
                            ports=[5002], port_bindings={5002:5002},
                            volumes=[volume_dir])
    actuator = net.addDocker("actuator", ip="192.168.0.3/24",dimage="modbusnet:latest",
                            ports=[5003], port_bindings={5003:5003},
                            volumes=[volume_dir])

    # Switches
    s1 = net.addSwitch("s1", cls=OVSSwitch, failMode="standalone")

    # Links
    net.addLink(sensor, s1, cls=TCLink, delay=delay, bw=bandwidth)
    net.addLink(manager, s1, cls=TCLink, delay=delay, bw=bandwidth)
    net.addLink(actuator, s1, cls=TCLink, delay=delay, bw=bandwidth)

    # Run modbus scripts
    info(sensor.cmd("python3.10 -m cosim.modbus_pp.voltage_sensor 0.0.0.0 5001 172.17.0.1 5000 &"))
    info(manager.cmd("python3.10 -m cosim.modbus_pp.voltage_manager 192.168.0.1 5001 192.168.0.3 5003 &"))
    info(actuator.cmd("python3.10 -m cosim.modbus_pp.voltage_actuator 0.0.0.0 5003 172.17.0.1 5000 &"))

    net.start()
    net.ping([sensor, manager, actuator])
    CLI(net)
    net.stop()
    

if __name__ == "__main__":
    main(None)