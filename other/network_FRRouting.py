import subprocess

from mininet.net import Containernet
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel

def configure_rip(container_name, network):
    rip_config = f"""
    vtysh -c 'configure terminal' \
          -c 'router rip' \
          -c 'version 2' \
          -c 'network {network}' \
          -c 'redistribute connected' \
          -c 'exit'
    """
    subprocess.run(f"docker exec {container_name} {rip_config}", shell=True)


if __name__ == "__main__":
    setLogLevel('info')
    
    net = Containernet(link=TCLink)
    
    sysctl_values = {"net.ipv4.ip_forward": 1}
    start_command = "nohup /usr/lib/frr/docker-start > frr.log &"
    volume_values = ["/lib/modules:/lib/modules:ro"]
    caps_values = ["ALL"]
    frr_image = "quay.io/frrouting/frr:8.4.5"
    
    # Routers
    r1 = net.addDocker("r1", ip=None,
                       dimage=frr_image,
                       sysctls=sysctl_values,
                       volumes=volume_values,
                       cap_add=caps_values)
    r2 = net.addDocker("r2", ip=None,
                       dimage=frr_image,
                       sysctls=sysctl_values,
                       volumes=volume_values,
                       cap_add=caps_values)
    
    # Switches
    #s1 = net.addSwitch('s1')
    #s2 = net.addSwitch('s2')

    # Hosts
    d1 = net.addHost("d1", dimage="ubuntu:trusty",
                     ip="192.168.0.2/24",
                     defaultRoute="via 192.168.0.1")
    d2 = net.addHost("d2", dimage="ubuntu:trusty",
                     ip="192.168.1.2/24",
                     defaultRoute="via 192.168.1.1")    
    
    # Router-Router links
    net.addLink(r1, r2)
    
    # Router-Switch links
    #net.addLink(r1, s1)
    #net.addLink(r2, s2)

    # Host-Switch links
    net.addLink(d1, r1)
    net.addLink(d2, r2)
    
    net.build()
    
    r1.cmd("ifconfig r1-eth0 192.168.0.1 netmask 255.255.255.0")
    r1.cmd("ifconfig r1-eth1 10.0.0.1 netmask 255.255.255.252")
    r2.cmd("ifconfig r2-eth0 192.168.1.1 netmask 255.255.255.0")
    r2.cmd("ifconfig r2-eth1 10.0.0.2 netmask 255.255.255.252")
    
    r1.cmd(start_command)
    r2.cmd(start_command)
    
    configure_rip("mn.r1", "192.168.0.0/24")
    configure_rip("mn.r2", "192.168.1.0/24")
    
    try:
        net.start()
        net.ping([d1, d2])
        CLI(net)
    finally:
        net.stop()
    

 