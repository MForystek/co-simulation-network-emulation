from mininet.net import Containernet
from mininet.node import OVSSwitch
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel

from cosim.utils import SRC_PATH

def main(args):
    if args is None:
        delay = "0ms"
        bandwidth = 1.0
    else:
        delay = args.delay
        bandwidth = args.bandwidth
    
    setLogLevel('info')

    net = Containernet()

    code_dir = str(SRC_PATH)
    volume_dir = code_dir + ":/app"

    # Hosts
    d1 = net.addDocker("d1", ip="192.168.0.1/24", dimage="jsonnet:latest",
                        ports=[2137], port_bindings={2137:2137},
                        volumes=[volume_dir])
    d2 = net.addDocker("d2", ip="192.168.0.2/24",dimage="jsonnet:latest",
                        ports=[4321], port_bindings={4321:4321},
                        volumes=[volume_dir])
    info(d1.cmd('python3.10 -m cosim.json_pp.data_forwarder 172.17.0.2 2137 192.168.0.2 1337 &'))
    info(d2.cmd('python3.10 -m cosim.json_pp.data_forwarder 192.168.0.2 1337 172.17.0.1 3721 &'))

    # Switches
    s1 = net.addSwitch('s1', cls=OVSSwitch, failMode="standalone")
    s2 = net.addSwitch('s2', cls=OVSSwitch, failMode="standalone")

    #Links
    net.addLink(d1, s1, cls=TCLink, delay=delay, bw=bandwidth)
    net.addLink(d2, s2, cls=TCLink, delay=delay, bw=bandwidth)
    net.addLink(s1, s2, cls=TCLink, delay=delay, bw=bandwidth)

    net.start()
    net.ping([d1, d2])
    CLI(net)
    net.stop()
    
    
if __name__ == "__main__":
    main(None)