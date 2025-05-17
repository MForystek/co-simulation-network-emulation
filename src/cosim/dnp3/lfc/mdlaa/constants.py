import numpy as np

####################################
# COMMON CONSTANTS
####################################

MILLI = 1e-3
MICRO = 1e-6

NOMINAL_FREQ = 60   # HZ

# Parameters
Tini = 20               # Initialization window (past steps to match)
Nap = 40                # Prediction horizon (future steps to optimize)
Nac = 10                # Control horizon (steps to apply)
Omega_r_weight = 1.025  # Attack success threshold over 1 p.u.
Q_weight = 1e5          # Weight for frequency deviation penalty
R_weight = 1e1          # Weight for attack effort penalty

step_time = 100         # ms


####################################
# MDLAA 39 Bus Constants
####################################

NUM_LOAD_BUSES_39BUS = 18
NUM_GEN_BUSES_39BUS = 10
NUM_LOADS_MASTER1_39BUS = 10 # number of load buses attacked by the master1
NUM_LOADS_MASTER2_39BUS = 8 # number of load buses attacked by the master2
NUM_ATTACKED_LOAD_BUSES_39BUS = NUM_LOADS_MASTER1_39BUS + NUM_LOADS_MASTER2_39BUS # total number of attacked load buses
# Load numbers:         15   16   20   21    3   18   25    4     7     8    23     24    26   27   28    29    12   39
NOMINAL_PS_39BUS = np.array([320, 329, 628, 274, 322, 158, 224, 500, 233.8, 522, 247.5, 308.6, 139, 281, 206, 283.5, 7.5, 1104]) # MW

# Parameters
Ta_39BUS = 1000   # Historical data length (must be >> Tini + Nap)
wait_iters_39BUS = -300 # number of iterations to skip due to waiting for the system to settle

max_attack_39BUS = (1 + 0.4) * np.ones(NUM_LOAD_BUSES_39BUS) # Max x% load alteration per bus
min_attack_39BUS = (1 - 0.4) * np.ones(NUM_LOAD_BUSES_39BUS) # Min x% load alteration per bus


####################################
# MDLAA Kundur Constants
####################################

NUM_LOAD_BUSES_KUNDUR = 2
NUM_GEN_BUSES_KUNDUR = 4
NUM_LOADS_MASTER1_KUNDUR = 1 # number of load buses attacked by the master1
NUM_LOADS_MASTER2_KUNDUR = 1 # number of load buses attacked by the master2
NUM_ATTACKED_LOAD_BUSES_KUNDUR = NUM_LOADS_MASTER1_KUNDUR + NUM_LOADS_MASTER2_KUNDUR  # total number of attacked load buses
# Load numbers:         1    2
NOMINAL_PS_KUNDUR = np.array([967, 1767]) # MW

# Parameters
Ta_KUNDUR = 360    # Historical data length (must be >> Tini + Nap)
wait_iters_KUNDUR = -100 # number of iterations to skip due to waiting for the system to settle

max_attack_KUNDUR = (1 + 0.15) * np.ones(NUM_LOAD_BUSES_KUNDUR) # Max x% load alteration per bus
min_attack_KUNDUR = (1 - 0.15) * np.ones(NUM_LOAD_BUSES_KUNDUR) # Min x% load alteration per bus