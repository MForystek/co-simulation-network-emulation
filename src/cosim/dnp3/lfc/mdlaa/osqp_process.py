import time
import numpy as np
import osqp

from multiprocessing.connection import Connection
from scipy.sparse import csc_matrix

from cosim.mylogging import getLogger
from cosim.dnp3.lfc.mdlaa.constants import *


log = getLogger(__name__, "logs/osqp.log")

class OSQPSolver:
    def __init__(self):
        self._osqp = osqp.OSQP()
        self._osqp_parameters_prepared = False
        self._osqp_constraints_constructed = False
        
        self._num_of_osqp_solved = 0      # excluding the first calculation
        self._avg_osqp_solving_time = 0.0
    
        
    def prepare_OSQP_parameters(self, U, Y):
        log.info("Preparing OSQP parameters...")
        self._attack_history = U[:, :Tini]
        self._freq_history = Y[:, :Tini]
        
        HU = self._build_hankel(U, Tini + Nap) # Shape: [(Tini+Nap)*num_load_buses, Ta-Tini-Nap+1]
        HY = self._build_hankel(Y, Tini + Nap) # Shape: [(Tini+Nap)*num_gen_buses, Ta-Tini-Nap+1]
        self._assert_Hankel_full_rank(np.vstack([HU, HY]))

        # Split into past/future blocks
        self._Up = HU[:Tini*NUM_LOAD_BUSES, :]
        self._Uf = HU[Tini*NUM_LOAD_BUSES:(Tini+Nap)*NUM_LOAD_BUSES, :]
        self._Yp = HY[:Tini*NUM_GEN_BUSES, :]
        self._Yf = HY[Tini*NUM_GEN_BUSES:(Tini+Nap)*NUM_GEN_BUSES, :]
        
        # Construct OSQP parameters
        self._H = self._Yf.T @ np.kron(np.eye(Nap), Q) @ self._Yf + self._Uf.T @ np.kron(np.eye(Nap), R) @ self._Uf
        self._f = -self._Yf.T @ np.kron(np.eye(Nap), Q) @ np.tile(Omega_r, (Nap * NUM_GEN_BUSES, 1))
        self._osqp_parameters_prepared = True
            
    
    def _build_hankel(self, data, L):
        cols = data.shape[1] - L + 1  # Number of columns in Hankel matrix
        H = np.zeros((L * data.shape[0], cols))
        for i in range(L):
            row_block = data[:, i:i+cols]
            H[i*data.shape[0]:(i+1)*data.shape[0], :] = row_block
        return H
    
    
    def _assert_Hankel_full_rank(self, combined_Hankel):
        rank = np.linalg.matrix_rank(combined_Hankel)
        log.info(f"Rank of combined Hankel matrix: {rank} / {combined_Hankel.shape[1]} columns")
        assert rank == combined_Hankel.shape[1], "Hankel matrix is not full rank"
    
    
    def construct_constraints(self):
        assert self._osqp_parameters_prepared, "OSQP parameters not prepared!"
        log.info("Constructing OSQP constraints...")
        self._u_ini = self._attack_history.flatten(order='F')  # Column-wise flattening
        self._y_ini = self._freq_history.flatten(order='F')
        
        # [Up; Yp] * g = [u_ini; y_ini]
        self._A_eq = np.vstack([self._Up, self._Yp])
        self._lb_eq = np.hstack([self._u_ini, self._y_ini])
        self._ub_eq = self._lb_eq 
        # min_attack <= Uf * g <= max_attack (repeated for N steps)
        self._A_ineq = self._Uf
        self._ub_ineq = np.tile(max_attack, Nap) # Upper bound - twice the nominal power
        self._lb_ineq = np.tile(min_attack, Nap) # Lower bound - half the nominal power
        # Combine constraints
        self._A = np.vstack([self._A_eq, self._A_ineq])
        self._lb = np.hstack([self._lb_eq, self._lb_ineq])
        self._ub = np.hstack([self._ub_eq, self._ub_ineq])
        self._assert_residuals_small_enough()
        self._osqp_constraints_constructed = True
    
    
    def _assert_residuals_small_enough(self):
        # Checking if [u_ini; y_ini] lies in the column space of [Up; Yp]
        # Solving least-squares: Find g such that A_eq * g ≈ target
        g_ls = np.linalg.lstsq(self._A_eq, self._lb_eq, rcond=None)[0]
        residual = np.linalg.norm(self._A_eq @ g_ls - self._lb_eq)
        log.info(f"Least-squares residual: {residual}")
        assert residual <= 1e-6, "Initial conditions incompatible with historical data!"   
   
   
    def setup_solve(self):
        assert self._osqp_constraints_constructed, "OSQP constraints not constructed!"
        log.info("Setting up OSQP problem...")
        self._osqp.setup(
            P=csc_matrix(self._H), q=self._f.flatten(),
            A=csc_matrix(self._A), l=self._lb, u=self._ub,
            verbose=False)
        
        log.info("Solving OSQP problem...")
        result = self._osqp.solve()
        return self._return_attacks_or_skip_if_infeasible(result)
       
       
    def update_solve(self, attack_history, freq_history):
        self._u_ini = attack_history.flatten(order='F')
        self._y_ini = freq_history.flatten(order='F')
        self._lb_eq = np.hstack([self._u_ini, self._y_ini])
        self._ub_eq = self._lb_eq   
        self._lb = np.hstack([self._lb_eq, self._lb_ineq])
        self._ub = np.hstack([self._ub_eq, self._ub_ineq]) 
        self._osqp.update(l=self._lb, u=self._ub)
        
        log.info("Solving OSQP problem...")
        osqp_solving_start_time = time.time_ns()
        result = self._osqp.solve()
        self._log_osqp_solving_time(osqp_solving_start_time)
        return self._return_attacks_or_skip_if_infeasible(result)
    
    
    def _return_attacks_or_skip_if_infeasible(self, result):
        if result.info.status != 'solved':
            log.warning(f"Optimization failed. Status: {result.info.status}. Skipping...")
            return {'skip': True}
        return {'attacks': self._extract_optimal_attacks(result.x)}
    
    
    def _extract_optimal_attacks(self, g_optimal):
        log.info("OSQP Solved successfully")
        u_opt = (self._Uf @ g_optimal).reshape(Nap, NUM_LOAD_BUSES)
        optimal_attacks_to_apply = u_opt[:Nac, :]
        return optimal_attacks_to_apply
       
    
    def _log_osqp_solving_time(self, osqp_solving_start_time):
        osqp_solving_time = (time.time_ns() - osqp_solving_start_time) * MICRO # in ms
        self._avg_osqp_solving_time = (self._avg_osqp_solving_time * self._num_of_osqp_solved + osqp_solving_time) / (self._num_of_osqp_solved + 1)
        self._num_of_osqp_solved += 1
        log.info(f"OSQP solving time avg: {self._avg_osqp_solving_time:.0f} ms, last: {osqp_solving_time:.0f} ms")
        

def solving_osqp(child_pipe: Connection):    
    osqp_solver = OSQPSolver()
    
    # Read the first data to initialize the solver
    setup_data = child_pipe.recv()
    # Initialize the solver
    osqp_solver.prepare_OSQP_parameters(setup_data['U'], setup_data['Y'])
    osqp_solver.construct_constraints()
    result = osqp_solver.setup_solve()
    # Sned the result of first calculation
    child_pipe.send(result)
    
    while True:
        if not child_pipe.poll():
            time.sleep(step_time * MILLI / 2)
            continue
        
        data = child_pipe.recv()
        result = osqp_solver.update_solve(data['attack_history'], data['freq_history'])
        child_pipe.send(result)
