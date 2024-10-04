from mininet.net import Containernet
from mininet.node import Docker
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel

class LinuxRouter(Docker):
    def start(self):
        self.cmd("sysctl net.ipv4.conf.default.rp_filter=1")
        self.cmd("sysctl net.ipv4.conf.all.rp_filter=1")
        self.cmd("sysctl net.ipv4.ip_forward=1")
        super(LinuxRouter, self).start()
        
    def terminate(self):
        self.cmd("sysctl net.ipv4.conf.default.rp_filter=0")
        self.cmd("sysctl net.ipv4.conf.all.rp_filter=0")
        self.cmd("sysctl net.ipv4.ip_forward=0")
        super(LinuxRouter, self).terminate()
        

if __name__ == "__main__":
    setLogLevel('info')
    
    net = Containernet()
    
    # Routers
    r1 = net.addDocker("r1", dimage="ubuntu:trusty",
                  cls=LinuxRouter,
                  ip=None,
                  network_mode="host")
    r2 = net.addDocker("r2", dimage="ubuntu:trusty",
                  cls=LinuxRouter,
                  ip=None,
                  network_mode="host")
    
    # Switches
    s1 = net.addSwitch('s1')
    s2 = net.addSwitch('s2')

    # Hosts
    d1 = net.addDocker("d1", dimage="ubuntu:trusty",
                       ip="192.168.0.2/24",
                       defaultRoute="via 192.168.0.1",
                       network_mode="host")
    d2 = net.addDocker("d2", dimage="ubuntu:trusty",
                       ip="192.168.1.2/24",
                       defaultRoute="via 192.168.1.1",
                       network_mode="host")    
    
    # Router-Router links
    net.addLink(r1, r2,
                intfName1="r1-eth2",
                intfName2="r2-eth2",
                params1={"ip": "10.0.0.1/30"},
                params2={"ip": "10.0.0.2/30"})
    
    # Router-Switch links
    net.addLink(r1, s1,
                intfName1="r1-eth1",
                params1={"ip": "192.168.0.1/24"})
    net.addLink(r2, s2,
                intfName1="r2-eth1",
                params1={"ip": "192.168.1.1/24"})

    # Host-Switch links
    net.addLink(d1, s1)
    net.addLink(d2, s2)
    
    try:
        net.start()
        
        info(r1.cmd("ip route add 192.168.1.0/24 via 10.0.1.1 dev r1-eth2"))
        info(r2.cmd("ip route add 192.168.0.0/24 via 10.0.0.1 dev r2-eth2"))
        
        net.ping([d1, d2])
        CLI(net)
    finally:
        net.stop()
    