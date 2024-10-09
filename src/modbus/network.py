import pathlib

from mininet.net import Containernet
from mininet.node import OVSSwitch
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel


setLogLevel('info')

net = Containernet() 

code_dir = str(pathlib.Path(__file__).parent.resolve())
volume_dir = code_dir + ":/app"

# Hosts
sensor = net.addDocker("sensor", ip="192.168.0.1/24", dimage="ubuntu20:latest",
                          ports=[5001], port_bindings={5001:5001},
                          volumes=[volume_dir])
manager = net.addDocker("manager", ip="192.168.0.2/24",dimage="ubuntu20:latest",
                        ports=[5002], port_bindings={5002:5002},
                        volumes=[volume_dir])
actuator = net.addDocker("actuator", ip="192.168.0.3/24",dimage="ubuntu20:latest",
                        ports=[5003], port_bindings={5003:5003},
                        volumes=[volume_dir])

# Switches
s1 = net.addSwitch("s1", cls=OVSSwitch, failMode="standalone")

# Links
net.addLink(sensor, s1)
net.addLink(manager, s1, cls=TCLink, delay="250ms", bw=0.1)
net.addLink(actuator, s1)

# Run modbus scripts
info(sensor.cmd("python3.10 /app/voltage_sensor.py 0.0.0.0 5001 172.17.0.1 5000 &"))
info(manager.cmd("python3.10 /app/voltage_manager.py 192.168.0.1 5001 192.168.0.3 5003 &"))
info(actuator.cmd("python3.10 /app/voltage_actuator.py 0.0.0.0 5003 172.17.0.1 5000 &"))

net.start()
net.ping([sensor, manager, actuator])
CLI(net)
net.stop()