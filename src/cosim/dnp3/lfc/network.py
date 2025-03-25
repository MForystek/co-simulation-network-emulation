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
                            ports=[20003], port_bindings={20003:20003},
                            volumes=[volume_dir],
                            network_mode="bridge")
    attacker = net.addDocker("attacker", ip="192.168.0.2/24", dimage="dnp3:latest",
                             ports=[20004], port_bindings={20004:20004},
                             volumes=[volume_dir],
                             network_mode="bridge")
  
    # Run dnp3 scripts
    info(master.cmd("python3 -m cosim.dnp3.lfc.LFC_master &"))
    #info(attacker.cmd("python3 -m cosim.dnp3.lfc.mdlaa.mulproc_MDLAA_controller &"))
    
    net.start()
    CLI(net)
    net.stop()
    

if __name__ == "__main__":
    main(None)