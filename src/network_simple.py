import time

from mininet.net import Containernet
from mininet.node import OVSSwitch
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel


code_dir = "/home/forystmj/research/src/"

if __name__ == "__main__":
    setLogLevel('info')
    
    net = Containernet() 

    # Hosts
    d1 = net.addDocker("d1", ip="192.168.0.1/24", dimage="ubuntu20:latest",
                       ports=[2137], port_bindings={2137:2137},
                       volumes=[code_dir + ":/app"])
    d2 = net.addDocker("d2", ip="192.168.0.2/24",dimage="ubuntu20:latest",
                       ports=[4321], port_bindings={4321:4321},
                       volumes=[code_dir + ":/app"])
    info(d1.cmd('python3.10 /app/data_forwarder.py 172.17.0.2 2137 192.168.0.2 1337 logs.log &'))
    info(d2.cmd('python3.10 /app/data_forwarder.py 192.168.0.2 1337 172.17.0.1 3721 logs.log &'))
    
    # Switches
    s1 = net.addSwitch('s1', cls=OVSSwitch, failMode="standalone")
    s2 = net.addSwitch('s2', cls=OVSSwitch, failMode="standalone")
    
    #Links
    net.addLink(d1, s1)
    net.addLink(d2, s2)
    net.addLink(s1, s2, cls=TCLink, delay="500ms", bw=0.1)

    net.start()
    net.ping([d1, d2])
    CLI(net)
    net.stop()

 