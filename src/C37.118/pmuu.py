from synchrophasor.pmu import Pmu

pmu = Pmu(ip="127.0.0.1", port=2137)
pmu.set_configuration()
pmu.set_header()

pmu.run()

while True:
    if pmu.clients:
        pmu.send(pmu.ieee_data_sample)
        
pmu.join()
