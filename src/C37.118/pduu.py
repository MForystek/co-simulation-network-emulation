from synchrophasor.pdc import Pdc

pdc = Pdc(pdc_id=7, pmu_ip="127.0.0.1", pmu_port=2137)
pdc.run()

header = pdc.get_header()
config = pdc.get_config()

pdc.start()

while True:
    data = pdc.get()
    print(data)
    if not data:
        pdc.quit()
        break