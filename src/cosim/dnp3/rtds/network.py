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
    master = net.addDocker("master", ip="192.168.0.1/24", dimage="dnp3:latest",
                            ports=[20001], port_bindings={20001:20001},
                            volumes=[volume_dir],
                            network_mode="bridge")
    # outstations = net.addDocker("outstation", ip="192.168.0.2/24", dimage="dnp3:latest",
    #                         ports=[20002], port_bindings={20002:20002},
    #                         volumes=[volume_dir],
    #                         network_mode="bridge")
    
    # Switches
    s1 = net.addSwitch("s1", cls=OVSSwitch, failMode="standalone")

    # Links
    net.addLink(master, s1, cls=TCLink, delay=delay, bw=bandwidth)
    #net.addLink(outstations, s1, cls=TCLink, delay=delay, bw=bandwidth)
    
    # Run dnp3 scripts
    info(master.cmd("python3 -m cosim.dnp3.rtds.master &"))
    #info(outstations.cmd("python3 -m cosim.dnp3.rtds.power &"))
    
    
    net.start()
    #net.ping([outstations, master])
    CLI(net)
    net.stop()
    

if __name__ == "__main__":
    main(None)