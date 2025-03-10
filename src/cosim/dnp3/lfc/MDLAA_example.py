import numpy as np
import osqp
import time

from scipy.linalg import hankel
from scipy.sparse import csc_matrix

# System parameters
num_load_buses = 19 # number of attackable load buses
num_gen_buses = 10  # number of generator buses
Omega_r = 1.025     # Attack success threshold
Tini = 20           # Past samples for initial condition
Nap = 40            # Prediction horizon
Nac = 5             # Control horizon (steps to apply)
Ts = 0.1            # Sampling time (seconds)
Q = 1e5 * np.eye(num_gen_buses)             # Frequency deviation penalty
R = 1e1 * np.eye(num_load_buses)            # Attack effort penalty
max_attack = 0.03 * np.ones(num_load_buses) # Max x% load alteration per bus

# Simulate historical data collection (replace with real measurements)
T_data = 1000 # Total data points for Hankel matrices
U = np.random.randn(num_load_buses, T_data) * 0.1 # Random attacks
Y = np.random.randn(num_gen_buses, T_data) * 0.01 # Simulated frequency responses

# Build Hankel matrices for input (U) and output (Y)
def build_hankel(data, L):
    cols = data.shape[1] - L + 1  # Number of columns in Hankel matrix
    H = np.zeros((L * data.shape[0], cols))
    for i in range(L):
        row_block = data[:, i:i+cols]
        H[i*data.shape[0]:(i+1)*data.shape[0], :] = row_block
    return H
    #return hankel(data[:, :L], data[:, L-1:])


HU = build_hankel(U, Tini + Nap) # Shape: [(Tini+Nap)*num_load_buses, T_data-Tini-Nap+1]
HY = build_hankel(Y, Tini + Nap) # Shape: [(Tini+Nap)*num_gen_buses, T_data-Tini-Nap+1]

# Split into past/future blocks
Up = HU[:Tini*num_load_buses, :]
Uf = HU[Tini*num_load_buses:(Tini+Nap)*num_load_buses, :]
Yp = HY[:Tini*num_gen_buses, :]
Yf = HY[Tini*num_gen_buses:(Tini+Nap)*num_gen_buses, :]


def get_current_frequencies():
    # Replace with actual function to read frequencies
    return np.random.randn(num_gen_buses) * 0.01 + 1.0 # Simulated frequencies

current_attack = np.zeros(num_load_buses) # Track applied attacks


def attack(coeff):
    # Replace with actual function to apply attacks
    print("Attack!!! with coeff:", coeff)
   

# Initialize history buffers (replace with actual past data)
attack_history = np.zeros((num_load_buses, Tini))  # Stores Tini past attacks
freq_history = np.zeros((num_gen_buses, Tini))     # Stores Tini past frequencies   
 

for iter in range(10000):
    # Update history buffers (shift left and append new data)
    new_attack = current_attack.copy()
    new_freq = get_current_frequencies().copy()
    
    attack_history = np.roll(attack_history, -1, axis=1)
    attack_history[:, -1] = new_attack
    freq_history = np.roll(freq_history, -1, axis=1)
    freq_history[:, -1] = new_freq
    
    # Construct u_ini and y_ini from Tini past samples
    u_ini = attack_history.flatten(order='F')  # Column-wise flattening
    y_ini = freq_history.flatten(order='F')
    
    # Construct OSQP problem
    H = Yf.T @ np.kron(np.eye(Nap), Q) @ Yf + Uf.T @ np.kron(np.eye(Nap), R) @ Uf
    f = -Yf.T @ np.kron(np.eye(Nap), Q) @ np.tile(Omega_r, (Nap*num_gen_buses, 1))
    
    print(H.shape)
    print(f.shape)
        
    # Equality constraints: [Up; Yp] * g = [u_ini; y_ini]
    A_eq = np.vstack([Up, Yp])
    lb_eq = np.hstack([u_ini, y_ini])
    ub_eq = lb_eq.copy()
    
    # Inequality constraints: Uf * g <= max_attack (repeated for N steps)
    A_ineq = Uf
    ub_ineq = np.tile(max_attack, Nap)
    lb_ineq = -np.inf * np.ones_like(ub_ineq) # No lower bound
    
    # Combine constraints
    A = np.vstack([A_eq, A_ineq])
    lb = np.hstack([lb_eq, lb_ineq])
    ub = np.hstack([ub_eq, ub_ineq])

    
    # Solve with OSQP
    prob = osqp.OSQP()    
    prob.setup(
        P=csc_matrix(H),
        q=f.flatten(),
        A=csc_matrix(A),
        l=lb,
        u=ub,
        verbose=False
    )
    res = prob.solve()
    
    print(res.info.status)
    
    if res.info.status != 'solved':
        print('Optimization failed. Skipping...')
        continue
    
    # Extract optimal attack sequence (first Nac steps)
    g_opt = res.x
    u_opt = (Uf @ g_opt).reshape(Nap, num_load_buses)
    apply_attack = u_opt[:Nac, :]
    
    # Apply the attack via attack1() to attack19()
    for t in range(Nac):
        for bus in range(num_load_buses):
            coeff = apply_attack[t, bus]
            attack(coeff) # Call attack function
            
        # Update current attack vector
        current_attack = apply_attack[t, :]
        
        # Wait for next time step
        time.sleep(Ts)