import numpy as np

MILLI = 1e-3
MICRO = 1e-6

TOTAL_NUM_LOAD_BUSES = 2 # number of load buses
TOTAL_NUM_GEN_BUSES = 4  # number of generator buses
NUM_OF_LOADS_PRIMARY_HANDLER = 1 # number of load buses attacked by the primary handler
NUM_OF_LOADS_SECONDARY_HANDLER = 1 # number of load buses attacked by the secondary handler
NUM_ATTACKED_LOAD_BUSES = NUM_OF_LOADS_PRIMARY_HANDLER + NUM_OF_LOADS_SECONDARY_HANDLER # number of attackable load buses
NOMINAL_FREQ = 60   # HZ
# Load numbers:         1    2
NOMINAL_PS = np.array([967, 1767]) # MW


# Parameters
Ta = 360                # Historical data length (must be >> Tini + Nap)
Tini = 20               # Initialization window (past steps to match)
Nap = 40                # Prediction horizon (future steps to optimize)
Nac = 10                # Control horizon (steps to apply)
Omega_r_weight = 1.025  # Attack success threshold over 1 p.u.
Q_weight = 1e5          # Weight for frequency deviation penalty
R_weight = 1e1          # Weight for attack effort penalty
max_attack = (1 + 0.3) * np.ones(TOTAL_NUM_LOAD_BUSES) # Max x% load alteration per bus
min_attack = (1 - 0.3) * np.ones(TOTAL_NUM_LOAD_BUSES) # Min x% load alteration per bus


step_time = 100      # ms
waiting_iters = -100 # number of iterations to skip due to waiting for the system to settle
