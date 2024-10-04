import sys
import time
import logging
import socket
import socketserver
    

def get_data_handler(forward_addr):
    class DataHandler(socketserver.BaseRequestHandler):
        def handle(self):
            data = self.request.recv(1024).strip()
            logging.info(f"Received from {self.client_address[0]}")
            logging.info(data.decode("utf-8"))
            
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
    if len(sys.argv) != 6:
        logging.error(f"Wrong number of arguments. Should be 5, was {len(sys.argv) - 1}")
        exit(1)
    
    logging.basicConfig(
        filename=sys.argv[5],
        encoding="utf-8",
        filemode="a",
        level=logging.INFO,
        format="{asctime} - {levelname} - {message}",
        style="{",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True
    )
    
    # Forwarder 1
    # srv_addr = ("172.17.0.2", 2137)
    # forward_addr = ("192.168.0.2", 1337)
    
    # Forwarder 2
    # srv_addr = ("192.168.0.2", 1337)
    # forward_addr = ("172.17.0.1", 3721)
    
    srv_addr = (sys.argv[1], int(sys.argv[2]))
    forward_addr = (sys.argv[3], int(sys.argv[4]))
    
    wait_for_interface(srv_addr)
    with socketserver.TCPServer(srv_addr, get_data_handler(forward_addr)) as server:
        server.serve_forever()