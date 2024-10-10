# Power System and Network co-simulation

Requires Linux, tested on Ubuntu 24.01.  
Tested on Python3.10. 

## Install

Run the following commands in the folder of your choice:
```
sudo ./apt-setup.sh
python3 -m venv .venv
source ./.venv/bin/activate
pip install -r requirements.txt
```

## Run 

IMPORTANT: Ensure that the virtual environment is activated. 

### Network
In the first terminal use:
```
sudo -E env PATH=$PATH python3 network.py --type <protocol>
```
to run network simulation.

### Power System
In the second terminal use:
```
python3 power.py --type <protocol>
```
to run power system simulation.

NOTE: Possible values for \<protocol\> are: json, modbus, dnp3, c37.118