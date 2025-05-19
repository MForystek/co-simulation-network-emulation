import numpy as np
import logging
import sys

from multiprocessing import Process, Manager, Queue

from cosim.mylogging import getLogger
from cosim.dnp3.lfc.mdlaa.constants import MILLI, NOMINAL_FREQ, Tini, Nap, Nac, Omega_r_weight, step_time, \
                                           rnd_attack_ampl, sin_attack_init_ampl, sin_attack_gain, sin_attack_freq, \
                                           consts_39BUS, consts_KUNDUR
from cosim.dnp3.lfc.mdlaa.osqp_proc import osqp_process
from cosim.dnp3.lfc.mdlaa.master1_proc import master1_process
from cosim.dnp3.lfc.mdlaa.master2_proc import master2_process


np.random.seed(2137)
log = getLogger(__name__, "logs/MDLAA.log", level=logging.INFO)

        
class MDLAAHandler:
    def __init__(self, main_to_master1: Queue, main_to_master2: Queue, main_to_osqp:Queue, osqp_to_main:Queue, pow_sys_consts:dict):
        # Queues
        self._main_to_master1 = main_to_master1
        self._main_to_master2 = main_to_master2
        self._master_to_osqp = main_to_osqp
        self._osqp_to_master = osqp_to_main
        
        # System dependent constants
        self._NUM_GENS = pow_sys_consts['NUM_GENS']
        self._NUM_LOADS = pow_sys_consts['NUM_LOADS']
        self._NUM_LOADS_MASTER1 = pow_sys_consts['NUM_LOADS_MASTER1']
        self._NUM_ATTACKED_LOADS = pow_sys_consts['NUM_ATTACKED_LOADS']
        self._NOMINAL_PS = pow_sys_consts['NOMINAL_PS']
        self._Ta = pow_sys_consts['Ta']
        self._wait_iters = pow_sys_consts['wait_iters']
        self._max_attack = pow_sys_consts['max_attack']
        self._min_attack = pow_sys_consts['min_attack']
        self._MAX_ATTACK_ITER = self._Ta / Nac
        
        # Measurement phase variables and constants
        self._RND_ATTACK = rnd_attack_ampl    # pu of load
        self._SIN_AMPL_GAIN = sin_attack_gain # pu of load
        self._SIN_FREQ = sin_attack_freq      # rad/ms
        
        self._sin_ampl = sin_attack_init_ampl # pu of load
        self._sin_angles = np.random.uniform(0, 2*np.pi, self._NUM_ATTACKED_LOADS) # rad
        
        # Counters
        self._measurement_iter = self._wait_iters
        self._ka = Tini
        self._attack_to_apply = -1
        
        # MDLAA freq and attack storage
        self._curr_freqs = np.ones(self._NUM_GENS)
        self._curr_attack = np.ones(self._NUM_ATTACKED_LOADS, dtype=np.float32) # Used also to apply the attack through the second master station
    
        # History of max and min attacks
        self._all_max_attack = np.ones(self._NUM_ATTACKED_LOADS)
        self._all_min_attack = np.ones(self._NUM_ATTACKED_LOADS)
    
        # Data storage for historical attacks and frequencies
        self._U = np.empty([self._NUM_ATTACKED_LOADS, self._Ta])
        self._Y = np.empty([self._NUM_GENS, self._Ta])
        self._attack_history = np.ones([self._NUM_ATTACKED_LOADS, Tini]) # Stores Tini past attacks
        self._freq_history = np.ones([self._NUM_GENS, Tini])             # Stores Tini past frequencies 
        
    
    def process_data(self, incoming_data):
        if incoming_data is None:
            return
        
        self._read_frequencies(incoming_data)
        if self._is_MDLAA_successful():
            return 
        
        # MDLAA first phase - collect data
        if self._measurement_iter < self._Ta:
            self._execute_MDLAA_first_phase()
            return
        
        self._update_freq_history()
        
        # MDLAA second phase - predict attacks
        if self._attack_to_apply == -1:
            self._execute_MDLAA_second_phase()
            return
            
        # MDLAA third phase - apply attacks
        self._execute_MDLAA_third_phase()

    
    def _read_frequencies(self, incoming_data):
        # TODO check if assigning one by one is necessary or can assign directly to curr_freqs
        freqs = [incoming_data[key][1] for key in range(self._NUM_GENS)]
        for i in range(self._NUM_GENS):
            self._curr_freqs[i] = freqs[i] * MILLI
        log.info(f"Freqs: {['{0:.5f}'.format(i) for i in self._curr_freqs.tolist()]}")
        self._curr_freqs = self._curr_freqs / NOMINAL_FREQ
    
    def _is_MDLAA_successful(self):   
        for freq in self._curr_freqs:
            if freq >= Omega_r_weight:
                log.warning(f"MDLAA SUCCESSFUL: {self._curr_freqs * NOMINAL_FREQ}")
                return True
        return False
    
        
    # ---First phase---
    def _execute_MDLAA_first_phase(self):
        log.info(f"Iter: {self._measurement_iter}")
        if self._measurement_iter >= 0:
            self._generate_and_apply_random_attack()
            self._collect_measurements()
        self._measurement_iter += 1           
    
    def _generate_and_apply_random_attack(self):
        # Sinus attack for DLAA like behaviour, random attack to make Hankel matrix full rank by avoiding repetitions
        sin_attack = np.sin(self._sin_angles) * self._sin_ampl
        rnd_attack = np.random.uniform(-self._RND_ATTACK, self._RND_ATTACK, self._NUM_ATTACKED_LOADS)
        self._curr_attack = 1 + sin_attack + rnd_attack # Add to 1 because attack is added to nominal load
        
        self._sin_angles += self._SIN_FREQ * step_time
        self._sin_ampl += self._SIN_AMPL_GAIN
        self._do_attack()
    
    def _collect_measurements(self):
        # Freqs delayed by one step and attacks ended one step faster,
        # because the attack at t affects the frequency at t+1
        if self._measurement_iter < self._Ta:
            self._U[:, self._measurement_iter] = self._curr_attack
            log.debug(f"Attack loads pu: {self._curr_attack.tolist()}")
            log.debug(f"Loads: {['{0:.4f}'.format(i) for i in self._U[:, self._measurement_iter].tolist() * self._NOMINAL_PS]}")    
        if self._measurement_iter > 0:
            self._Y[:, self._measurement_iter-1] = self._curr_freqs
            log.debug(f"Freqs: {['{0:.5f}'.format(i) for i in self._Y[:, self._measurement_iter-1].tolist() * NOMINAL_FREQ]}")  
     
    
    # ---Second phase---
    def _execute_MDLAA_second_phase(self):
        self._exit_if_max_attack_reached()
        log.info(f"Attack starts from index: {self._ka}")
        
        if self._ka == Tini:
            self._master_to_osqp.put({'U': self._U, 'Y': self._Y})
            self._attack_history = self._U[:, :Tini]
            self._freq_history = self._Y[:, :Tini]
        self._master_to_osqp.put({'attack_history': self._attack_history, 'freq_history': self._freq_history})
        OSQP_result = self._osqp_to_master.get()
        self._ka += Nac

        # If problem infeasible, apply Nac random attacks then skip
        if 'skip' in OSQP_result:
            for i in range(Nac):
                self._generate_and_apply_random_attack()
                self._update_attack_history()
            return
        
        # Prepare for the attacks execution
        self._optimal_attacks_to_apply = OSQP_result['attacks']
        self._attack_to_apply = 0   
    
    
    # ---Third phase---
    def _execute_MDLAA_third_phase(self):
        self._apply_predicted_attack()
        self._update_attack_history()
        if self._attack_to_apply == Nac-1:
            self._attack_to_apply = -1
        else:
            self._attack_to_apply += 1
    
    def _apply_predicted_attack(self):
        self._curr_attack = self._optimal_attacks_to_apply[:, self._attack_to_apply]
        log.debug(f"Success, attack: {[float(load) for load in self._curr_attack] * self._NOMINAL_PS}")
        self._do_attack()


    # ---Attack handling---
    def _do_attack(self):
        self._correct_attacks_beyond_bounds()
        self._update_and_log_all_time_max_min_attacks()
        self._send_attack_to_outstation()
    
    def _correct_attacks_beyond_bounds(self):
        for i in range(self._NUM_ATTACKED_LOADS):
            if self._curr_attack[i] > self._max_attack[i]:
                log.debug(f"Attack {i} is above the max_attack: {self._curr_attack[i]} > {self._max_attack[i]}")
                self._curr_attack[i] = self._max_attack[i]
            elif self._curr_attack[i] < self._min_attack[i]:
                log.debug(f"Attack {i} is below the min_attack: {self._curr_attack[i]} < {self._min_attack[i]}")
                self._curr_attack[i] = self._min_attack[i] 

    def _send_attack_to_outstation(self):
        for i in range(self._NUM_LOADS_MASTER1):
            self._main_to_master1.put((40, 4, i, float(self._curr_attack[i])))
        self._main_to_master2.put(self._curr_attack)
        log.debug(f"Doing DLAA: {self._curr_attack.tolist()}")


    # ---History updates ---
    def _update_freq_history(self):
        self._freq_history = np.roll(self._freq_history, -1, axis=1)
        self._freq_history[:, -1] = self._curr_freqs
    
    def _update_attack_history(self):
        self._attack_history = np.roll(self._attack_history, -1, axis=1)
        self._attack_history[:, -1] = self._curr_attack


    # ---Failure handling---    
    def _exit_if_max_attack_reached(self):
        if self._ka > self._Ta - Nap:
            log.error("MDLAA exceeded max attack iterations. Stopping...")
            self._main_to_master1.put(-1)
            self._main_to_master2.put(-1)
            self._master_to_osqp.put(-1)
            exit(0)


    # ---Logging---    
    def _update_and_log_all_time_max_min_attacks(self):
        for i in range(self._NUM_ATTACKED_LOADS):
            if self._curr_attack[i] > self._all_max_attack[i]:
                self._all_max_attack[i] = self._curr_attack[i]
            elif self._curr_attack[i] < self._all_min_attack[i]:
                self._all_min_attack[i] = self._curr_attack[i]
        log.debug(f"Max attacks: {self._all_max_attack.tolist() * self._NOMINAL_PS}")
        log.debug(f"Min attacks: {self._all_min_attack.tolist() * self._NOMINAL_PS}")  
    

def main(pow_sys_consts):    
    queue_manager = Manager()
    master_to_osqp = queue_manager.Queue()
    osqp_to_master = queue_manager.Queue()
    master1_to_main = queue_manager.Queue()
    main_to_master1 = queue_manager.Queue()
    main_to_master2 = queue_manager.Queue()
    
    master1 = Process(target=master1_process, args=(main_to_master1, master1_to_main, step_time))
    master1.start()
    master2 = Process(target=master2_process, args=(main_to_master2, step_time, pow_sys_consts))
    master2.start()
    osqp = Process(target=osqp_process, args=(master_to_osqp, osqp_to_master, pow_sys_consts))    
    osqp.start()
    log.info("Processes started")
    
    mdlaa_handler = MDLAAHandler(main_to_master1=main_to_master1, main_to_master2=main_to_master2,
                                 main_to_osqp=master_to_osqp, osqp_to_main=osqp_to_master,
                                 pow_sys_consts=pow_sys_consts)
    
    while True:
        data = master1_to_main.get()
        if type(data) == int and data == -1:
            break
        mdlaa_handler.process_data(data)
        
    master1.join()
    master2.join()
    osqp.join()
    queue_manager.shutdown() 
           

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 procs_MDLAA_ctrl.py <pow_sys_name>")
        sys.exit(1)
    elif sys.argv[1] == "39bus":
        pow_sys_consts = consts_39BUS
    elif sys.argv[1] == "kundur":
        pow_sys_consts = consts_KUNDUR
    else:
        print("Invalid power system name. Use '39bus' or 'kundur'.")
        sys.exit(1)
    main(pow_sys_consts)