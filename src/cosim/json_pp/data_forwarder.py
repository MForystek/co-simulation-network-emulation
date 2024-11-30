import sys
import time
import socket
import socketserver
    
from cosim import mylogging


logger = mylogging.getLogger("forwarder", "logs/j_pp_forwarder.log")


# Workaround to pass arguments to handle()
def get_data_handler(forward_addr):
    class DataHandler(socketserver.BaseRequestHandler):
        def handle(self):
            data = self.request.recv(1024).strip()
            logger.info(f"Received from {self.client_address[0]}")
            logger.info(data.decode("utf-8"))
            
            with socket.create_connection(forward_addr) as cli:
                cli.sendall(data)        
    return DataHandler
    

def wait_for_interface(srv_addr):
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(srv_addr)
            break
        except OSError as e:
            # CAUSE: Interface not initialized yet or address doesn't exist
            if e.errno == 99:
                time.sleep(0.5)
        

if __name__ == "__main__":
    if len(sys.argv) != 5:
        logger.error(f"Wrong number of arguments. Should be 4, was {len(sys.argv) - 1}")
        exit(1)
    
    srv_addr = (sys.argv[1], int(sys.argv[2]))
    forward_addr = (sys.argv[3], int(sys.argv[4]))
    
    wait_for_interface(srv_addr)
    with socketserver.TCPServer(srv_addr, get_data_handler(forward_addr)) as server:
        server.serve_forever()