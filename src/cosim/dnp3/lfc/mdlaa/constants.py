import numpy as np

####################################
# COMMON CONSTANTS
####################################

MILLI = 1e-3
MICRO = 1e-6

NOMINAL_FREQ = 60       # Hz

# Parameters
Tini = 20               # initialization window (past steps to match)
Nap = 40                # prediction horizon (future steps to optimize)
Nac = 10                # control horizon (steps to apply)
Omega_r_weight = 1.025  # attack success threshold over 1 pu of load
Q_weight = 1e5          # weight for frequency deviation penalty
R_weight = 1e1          # weight for attack effort penalty

rnd_attack_ampl = 0.001      # pu of load
sin_attack_init_ampl = 0.001 # pu of load
sin_attack_gain = 0.0001     # amplitude gain (in pu of load)
sin_attack_freq = np.pi/5000 # rad/ms

step_time = 100         # ms


####################################
# MDLAA 39 Bus Constants
####################################

NUM_GENS_39BUS = 10
NUM_LOADS_39BUS = 18
NUM_LOADS_MASTER1_39BUS = 10 # number of load buses attacked by the master1
NUM_LOADS_MASTER2_39BUS = 8  # number of load buses attacked by the master2
NUM_ATTACKED_LOADS_39BUS = NUM_LOADS_MASTER1_39BUS + NUM_LOADS_MASTER2_39BUS # total number of attacked load buses
# Load numbers:         15   16   20   21    3   18   25    4     7     8    23     24    26   27   28    29    12   39
NOMINAL_PS_39BUS = np.array([320, 329, 628, 274, 322, 158, 224, 500, 233.8, 522, 247.5, 308.6, 139, 281, 206, 283.5, 7.5, 1104]) # MW

# Parameters
Ta_39BUS = 1000         # historical data length (must be >> Tini + Nap)
wait_sec_39BUS = 30     # seconds to wait for the system to settle
wait_iters_39BUS = -int(wait_sec_39BUS / MILLI / step_time) # num of iterations to skip waiting for the system to settle

max_attack_39BUS = (1 + 0.4) * np.ones(NUM_LOADS_39BUS) # max x% load alteration per bus
min_attack_39BUS = (1 - 0.4) * np.ones(NUM_LOADS_39BUS) # min x% load alteration per bus


####################################
# MDLAA Kundur Constants
####################################

NUM_GENS_KUNDUR = 4
NUM_LOADS_KUNDUR = 2
NUM_LOADS_MASTER1_KUNDUR = 1 # number of load buses attacked by the master1
NUM_LOADS_MASTER2_KUNDUR = 1 # number of load buses attacked by the master2
NUM_ATTACKED_LOADS_KUNDUR = NUM_LOADS_MASTER1_KUNDUR + NUM_LOADS_MASTER2_KUNDUR # total number of attacked load buses
# Load numbers:         1    2
NOMINAL_PS_KUNDUR = np.array([967, 1767]) # MW

# Parameters
Ta_KUNDUR = 360          # historical data length (must be >> Tini + Nap)
wait_sec_KUNDUR = 10     # seconds to wait for the system to settle
wait_iters_KUNDUR = -int(wait_sec_KUNDUR / MILLI / step_time) # num of iterations to skip waiting for the system to settle

max_attack_KUNDUR = (1 + 0.15) * np.ones(NUM_LOADS_KUNDUR) # max x% load alteration per bus
min_attack_KUNDUR = (1 - 0.15) * np.ones(NUM_LOADS_KUNDUR) # min x% load alteration per bus


####################################
# CONSTANTS DICTIONARIES
####################################

consts_39BUS = {
    'NUM_GENS': NUM_GENS_39BUS,
    'NUM_LOADS': NUM_LOADS_39BUS,
    'NUM_LOADS_MASTER1': NUM_LOADS_MASTER1_39BUS,
    'NUM_LOADS_MASTER2': NUM_LOADS_MASTER2_39BUS,
    'NUM_ATTACKED_LOADS': NUM_ATTACKED_LOADS_39BUS,
    'NOMINAL_PS': NOMINAL_PS_39BUS,
    'Ta': Ta_39BUS,
    'wait_iters': wait_iters_39BUS,
    'max_attack': max_attack_39BUS,
    'min_attack': min_attack_39BUS
}

consts_KUNDUR = {
    'NUM_GENS': NUM_GENS_KUNDUR,
    'NUM_LOADS': NUM_LOADS_KUNDUR,
    'NUM_LOADS_MASTER1': NUM_LOADS_MASTER1_KUNDUR,
    'NUM_LOADS_MASTER2': NUM_LOADS_MASTER2_KUNDUR,
    'NUM_ATTACKED_LOADS': NUM_ATTACKED_LOADS_KUNDUR,
    'NOMINAL_PS': NOMINAL_PS_KUNDUR,
    'Ta': Ta_KUNDUR,
    'wait_iters': wait_iters_KUNDUR,
    'max_attack': max_attack_KUNDUR,
    'min_attack': min_attack_KUNDUR
}