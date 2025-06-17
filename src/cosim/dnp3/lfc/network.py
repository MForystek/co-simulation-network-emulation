from mininet.net import Containernet
from mininet.node import OVSSwitch
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
    
from cosim.utils import SRC_PATH


def main(args):
    delay = "0ms"
    loss = 0        # percentage
    bandwidth = 1.0 # in Mbps
    jitter = "0ms"
    
    if hasattr(args, 'delay'):
        delay = args.delay
    if hasattr(args, 'loss'):
        loss = args.loss
    if hasattr(args, 'bandwidth'):
        bandwidth = args.bandwidth
    if hasattr(args, 'jitter'):
        jitter = args.jitter

    setLogLevel('info')

    net = Containernet() 

    code_dir = str(SRC_PATH)
    volume_dir = code_dir + ":/app"

    # Hosts
    master_forwarder = net.addDocker("mstr_fwdr", ip="192.168.0.1/24", dimage="dnp3:latest",
                            ports=[20003], port_bindings={20003:20003},
                            volumes=[volume_dir],
                            network_mode="bridge")
    master = net.addDocker("master", ip="192.168.0.11/24", dimage="dnp3:latest",
                            ports=[20013], port_bindings={20013:20013},
                            volumes=[volume_dir],
                            network_mode="bridge")
    
    attacker = net.addDocker("attacker", ip="192.168.0.2/24", dimage="dnp3:latest",
                            ports=[20004], port_bindings={20004:20004},
                            volumes=[volume_dir],
                            network_mode="bridge")
  
    # Switches
    s1 = net.addSwitch("s1", cls=OVSSwitch, failMode="standalone")
    
    # Links
    net.addLink(master_forwarder, s1, cls=TCLink, delay=delay, bw=bandwidth, jitter=jitter, loss=loss)
    net.addLink(master, s1, cls=TCLink)
    
    # Run dnp3 scripts
    info(master_forwarder.cmd("python3 -m cosim.dnp3.lfc.LFC_forwarder &"))
    info(master.cmd("python3 -m cosim.dnp3.lfc.LFC_master &"))
    
    if args.attack == "slaa":
        info(attacker.cmd("python3 -m cosim.dnp3.lfc.SLAA_controller &"))
    elif args.attack == "dlaa":
        info(attacker.cmd("python3 -m cosim.dnp3.lfc.DLAA_controller &"))
    elif args.attack == "mdlaa":
        info(attacker.cmd("python3 -m cosim.dnp3.lfc.mdlaa.procs_MDLAA_ctrl 39bus &"))
    
    net.start()
    CLI(net)
    net.stop()
    

if __name__ == "__main__":
    main(None)