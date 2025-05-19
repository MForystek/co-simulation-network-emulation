import time
import numpy as np
import logging
import osqp
import scipy.sparse

from multiprocessing import Queue

from cosim.mylogging import getLogger
from cosim.dnp3.lfc.mdlaa.constants import Tini, Nap, Nac, Q_weight, R_weight, Omega_r_weight, MICRO


log = getLogger(__name__, "logs/osqp.log")
freq_log = getLogger("PredFreqLog", "logs/freqs.log", formatter=logging.Formatter('%(message)s'))

class OSQPSolver:
    def __init__(self, pow_sys_consts):
        self._NUM_GENS = pow_sys_consts['NUM_GENS']
        self._NUM_ATTACKED_LOADS = pow_sys_consts['NUM_ATTACKED_LOADS']
        self._max_attack = pow_sys_consts['max_attack']
        self._min_attack = pow_sys_consts['min_attack']
        
        self._osqp = osqp.OSQP()       
        self._osqp_parameters_prepared = False
        self._osqp_constraints_constructed = False
        
        self._num_of_osqp_solved = 0    # we won't count the first calculation
        self._avg_osqp_solving_time = 0.0
        self._last_solution = None      # store last solution for warm starting
    
        
    def prepare_OSQP_parameters(self, U, Y):
        log.info("Preparing OSQP parameters...")
        self._attack_history = U[:, :Tini]
        self._freq_history = Y[:, :Tini]
        
        HU = self._build_hankel(U, Tini + Nap) # shape: [(Tini+Nap)*num_load_buses, Ta-Tini-Nap+1]
        HY = self._build_hankel(Y, Tini + Nap) # shape: [(Tini+Nap)*num_gen_buses, Ta-Tini-Nap+1]
        self._assert_Hankel_full_rank(np.vstack([HU, HY]))

        # Split into past/future blocks
        self._Up = HU[:Tini*self._NUM_ATTACKED_LOADS, :]
        self._Uf = HU[Tini*self._NUM_ATTACKED_LOADS:, :]
        self._Yp = HY[:Tini*self._NUM_GENS, :]
        self._Yf = HY[Tini*self._NUM_GENS:, :]
        
        self._Up_sparse = scipy.sparse.csc_matrix(self._Up)
        self._Yp_sparse = scipy.sparse.csc_matrix(self._Yp)
        self._Yf_sparse = scipy.sparse.csc_matrix(self._Yf)
        self._Uf_sparse = scipy.sparse.csc_matrix(self._Uf)
        
        Q_sparse = Q_weight * scipy.sparse.eye(Nap * self._NUM_GENS, format='csc')
        R_sparse = R_weight * scipy.sparse.eye(Nap * self._NUM_ATTACKED_LOADS, format='csc')
        
        Omega_r = Omega_r_weight * np.ones(Nap * self._NUM_GENS)
        
        # Construct OSQP parameters
        YfTxQ = self._Yf_sparse.T @ Q_sparse
        self._H = 2 * (YfTxQ @ self._Yf_sparse + 
                    self._Uf_sparse.T @ R_sparse @ self._Uf_sparse)
        self._H = self._H.tocsc()
        self._f = -2 * (YfTxQ.toarray() @ Omega_r)
        self._osqp_parameters_prepared = True

    
    def _build_hankel(self, data, L):
        cols_num = data.shape[1] - L + 1  
        H = np.zeros((L * data.shape[0], cols_num))
        for i in range(L):
            row_block = data[:, i:i+cols_num]
            H[i*data.shape[0]:(i+1)*data.shape[0], :] = row_block
        return H
    
    
    def _assert_Hankel_full_rank(self, attacks_Hankel):
        rank = np.linalg.matrix_rank(attacks_Hankel)
        log.info(f"Rank of combined Hankel matrix: {rank} / {attacks_Hankel.shape[1]} columns")
        assert rank == attacks_Hankel.shape[1], "Attack vectors Hankel matrix is not full rank"
    
    
    def construct_constraints(self):
        assert self._osqp_parameters_prepared, "OSQP parameters not prepared!"
        log.info("Constructing OSQP constraints...")
        self._u_ini = self._attack_history.flatten(order='F')  # column-wise flattening
        self._y_ini = self._freq_history.flatten(order='F')    
            
        # [Up; Yp] * g = [u_ini; y_ini]
        self._A_eq = scipy.sparse.vstack([self._Up_sparse, self._Yp_sparse])
        self._lb_eq = np.hstack([self._u_ini, self._y_ini])
        self._ub_eq = self._lb_eq 
        # min_attack <= Uf * g <= max_attack (repeated for N steps)
        self._A_ineq = self._Uf_sparse
        self._ub_ineq = np.tile(self._max_attack, Nap) # upper bound for controlled load
        self._lb_ineq = np.tile(self._min_attack, Nap) # lower bound for controlled load
        # Combine constraints
        self._A = scipy.sparse.vstack([self._A_eq, self._A_ineq])
        self._A = self._A.tocsc()
        self._lb = np.hstack([self._lb_eq, self._lb_ineq])
        self._ub = np.hstack([self._ub_eq, self._ub_ineq])
        self._assert_residuals_small_enough()
        self._osqp_constraints_constructed = True
    
    
    def _assert_residuals_small_enough(self):
        # Checking if [u_ini; y_ini] lies in the column space of [Up; Yp]
        # Solving least-squares: Find g such that A_eq * g ≈ target
        A_eq_dense = self._A_eq.todense()
        g_ls = np.linalg.lstsq(A_eq_dense, self._lb_eq, rcond=None)[0]
        residual = np.linalg.norm(A_eq_dense @ g_ls - self._lb_eq)
        log.info(f"Least-squares residual: {residual}")
        assert residual <= 1e-6, "Initial conditions incompatible with historical data!"   
   
   
    def setup_solve(self):
        assert self._osqp_constraints_constructed, "OSQP constraints not constructed!"
        log.info("Setting up OSQP problem...")
        
        settings = {
            'verbose': False,
            'eps_abs': 5e-3,
            'eps_rel': 5e-3,
            'warm_start': True,
            #'adaptive_rho_interval': 25
        }
        
        self._osqp.setup(
            P=self._H, q=self._f.flatten(),
            A=self._A, l=self._lb, u=self._ub,
            **settings)
        
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
        # Update problem with warm start
        if self._last_solution is not None:
            self._osqp.warm_start(x=self._last_solution)
        
        log.info("Solving OSQP problem...")
        osqp_solving_start_time = time.time_ns()
        result = self._osqp.solve()
        self._log_osqp_solving_time(osqp_solving_start_time)
        
        return self._return_attacks_or_skip_if_infeasible(result)
    
    
    def _return_attacks_or_skip_if_infeasible(self, result):
        if result.info.status != 'solved':
            log.warning(f"Optimization failed. Status: {result.info.status}. Skipping...")
            self._last_solution = None
            return {'skip': True}
        self._last_solution = result.x  # store last solution for warm starting
        return {'attacks': self._extract_optimal_attacks(result.x)}
    
    
    def _extract_optimal_attacks(self, g_optimal):
        log.info("OSQP Solved successfully")
        pred_freqs = (self._Yf @ g_optimal).reshape(Nap, self._NUM_GENS).T
        freq_log.info(f"{pred_freqs[:, :Nac]}")
        u_opt = (self._Uf @ g_optimal).reshape(Nap, self._NUM_ATTACKED_LOADS).T
        optimal_attacks_to_apply = u_opt[:, :Nac]
        return optimal_attacks_to_apply
       
    
    def _log_osqp_solving_time(self, osqp_solving_start_time):
        osqp_solving_time = (time.time_ns() - osqp_solving_start_time) * MICRO # ms
        self._avg_osqp_solving_time = (self._avg_osqp_solving_time * self._num_of_osqp_solved + osqp_solving_time) / (self._num_of_osqp_solved + 1)
        self._num_of_osqp_solved += 1
        log.info(f"OSQP solving time avg: {self._avg_osqp_solving_time:.0f} ms, last: {osqp_solving_time:.0f} ms")
        

def osqp_process(main_to_osqp:Queue, osqp_to_main:Queue, pow_sys_consts):    
    osqp_solver = OSQPSolver(pow_sys_consts)
    
    # Read the first data to initialize the solver
    setup_data = main_to_osqp.get()
    # Initialize the solver
    osqp_solver.prepare_OSQP_parameters(setup_data['U'], setup_data['Y'])
    osqp_solver.construct_constraints()
    result = osqp_solver.setup_solve()
    # Send the result of first calculation
    osqp_to_main.put(result)
    
    while True:
        data = main_to_osqp.get()
        if type(data) == int and data == -1:
            log.info("Exiting OSQP process.")
            exit(0)
        
        result = osqp_solver.update_solve(data['attack_history'], data['freq_history'])
        try:
            osqp_to_main.put(result)
        except (EOFError, BrokenPipeError):
            log.info("Exiting OSQP process.")
            exit(0)