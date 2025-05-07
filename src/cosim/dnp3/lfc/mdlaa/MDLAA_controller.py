import numpy as np
import logging
import time

from multiprocessing import Process, Queue, Manager

from pydnp3.opendnp3 import GroupVariation

from cosim.mylogging import getLogger
from cosim.dnp3.lfc.mdlaa.constants import *
from cosim.dnp3.soe_handler import SOEHandlerAdjusted
from cosim.dnp3.master import MasterStation
from cosim.dnp3.lfc.mdlaa.secondary_MDLAA_handler import MDLAAHandlerSecondary
from cosim.dnp3.lfc.mdlaa.osqp_process import osqp_process


# Loggers
log = getLogger(__name__, "logs/MDLAA.log", level=logging.INFO)

        
class MDLAASOEHandler(SOEHandlerAdjusted):
    def __init__(self, log_file_path="logs/soehandler.log", soehandler_log_level=logging.INFO, station_ref=None,
                 attacks=np.ones(NUM_ATTACKED_LOAD_BUSES), master_to_osqp:Queue=None, osqp_to_master:Queue=None, *args, **kwargs):
        super().__init__(log_file_path, soehandler_log_level, station_ref, *args, **kwargs)
        # Constants
        self._NUM_OF_ATTACKED_LOADS = NUM_OF_LOADS_PRIMARY_HANDLER
        self._MAX_ATTACK_ITER = Ta / Nac
        self._RND_ATTACK_STRENGTH = 0.001 # pu
        
        # MDLAA freq and attack storage
        self._curr_freqs = np.ones(TOTAL_NUM_GEN_BUSES)
        self._curr_attack_temp = np.ones(NUM_ATTACKED_LOAD_BUSES)
        self._curr_attack = attacks # Used to apply the attack through the second master station
        
        # Counters
        self._measurement_iter = waiting_iters
        self._ka = Tini
        self._attack_to_apply = -1
    
        # History of max and min attacks
        self._all_max_attack = np.ones(NUM_ATTACKED_LOAD_BUSES)
        self._all_min_attack = np.ones(NUM_ATTACKED_LOAD_BUSES)
    
        # Data storage for historical attacks and frequencies
        self._U = np.empty([NUM_ATTACKED_LOAD_BUSES, Ta])
        self._Y = np.empty([TOTAL_NUM_GEN_BUSES, Ta])
        self._attack_history = np.ones([NUM_ATTACKED_LOAD_BUSES, Tini]) # Stores Tini past attacks
        self._freq_history = np.ones([TOTAL_NUM_GEN_BUSES, Tini])       # Stores Tini past frequencies 
        
        self._master_to_osqp = master_to_osqp
        self._osqp_to_master = osqp_to_master
        
        self._sinus_gain = 0.001
        self._sinus_angles = np.random.uniform(0, 2 * np.pi, NUM_ATTACKED_LOAD_BUSES)
    
    
    def _process_incoming_data(self, info_gv, visitor_index_and_value):        
        if info_gv in [GroupVariation.Group30Var6]:
            self._read_frequencies(visitor_index_and_value)
            if self._is_MDLAA_successful():
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
        for i in range(TOTAL_NUM_GEN_BUSES):
            self._curr_freqs[i] = visitor_index_and_value[i][1] * MILLI
        log.info(f"Freqs: {['{0:.5f}'.format(i) for i in self._curr_freqs.tolist()]}")
        self._curr_freqs = self._curr_freqs / NOMINAL_FREQ
            
        
    # ---First phase---
    def _execute_MDLAA_first_phase(self):
        log.info(f"Iter: {self._measurement_iter}")
        if self._measurement_iter >= 0:
            self._generate_and_apply_random_attack()
            self._collect_measurements()
        self._measurement_iter += 1           
    
    def _update_freq_history(self):
        self._freq_history = np.roll(self._freq_history, -1, axis=1)
        self._freq_history[:, -1] = self._curr_freqs
    
    def _update_attack_history(self):
        self._attack_history = np.roll(self._attack_history, -1, axis=1)
        self._attack_history[:, -1] = self._curr_attack
    
    
    # ---Attack handling---
    def _generate_and_apply_random_attack(self):
        self._curr_attack_temp = 1 + np.sin(self._sinus_angles) * self._sinus_gain \
            + np.random.uniform(-self._RND_ATTACK_STRENGTH, self._RND_ATTACK_STRENGTH, NUM_ATTACKED_LOAD_BUSES)
        self._sinus_angles += np.pi / 50
        self._sinus_gain += 0.0001
        self._do_attack()
    
    def _do_attack(self):
        self._correct_attacks_beyond_bounds()
        self._update_and_log_all_time_max_min_attacks()
        self._send_attack_to_outstation()
    
    def _correct_attacks_beyond_bounds(self):
        for i in range(NUM_ATTACKED_LOAD_BUSES):
            if self._curr_attack_temp[i] > max_attack[i]:
                log.debug(f"Attack {i} is above the max_attack: {self._curr_attack_temp[i]} > {max_attack[i]}")
                self._curr_attack_temp[i] = max_attack[i]
            elif self._curr_attack_temp[i] < min_attack[i]:
                log.debug(f"Attack {i} is below the min_attack: {self._curr_attack_temp[i]} < {min_attack[i]}")
                self._curr_attack_temp[i] = min_attack[i] 

    def _send_attack_to_outstation(self):
        # Assign one by one to not overwrite the _curr_attack list used in the second master station
        for i in range(NUM_ATTACKED_LOAD_BUSES):
            self._curr_attack[i] = self._curr_attack_temp[i]
        loads = self._curr_attack[:self._NUM_OF_ATTACKED_LOADS]
        for i in range(self._NUM_OF_ATTACKED_LOADS):
            self.station_ref.send_direct_point_command(40, 4, i, float(loads[i]))
        log.debug(f"Doing DLAA: {loads}")
    
    
    def _collect_measurements(self):
        # Freqs delayed by one step and attacks ended one step faster,
        # because the attack at t affects the frequency at t+1
        if self._measurement_iter < Ta:
            self._U[:, self._measurement_iter] = self._curr_attack
            log.debug(f"Attack loads pu: {self._curr_attack.tolist()}")
            log.debug(f"Loads: {['{0:.4f}'.format(i) for i in self._U[:, self._measurement_iter].tolist() * NOMINAL_PS]}")    
        if self._measurement_iter > 0:
            self._Y[:, self._measurement_iter-1] = self._curr_freqs
            log.debug(f"Freqs: {['{0:.5f}'.format(i) for i in self._Y[:, self._measurement_iter-1].tolist() * NOMINAL_FREQ]}")  
     
    
    # ---Second phase---
    def _execute_MDLAA_second_phase(self):
        self._exit_if_max_attack_reached()
        log.info(f"Attack start from index: {self._ka}")
        
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
        self._curr_attack_temp = self._optimal_attacks_to_apply[self._attack_to_apply, :]
        self._do_attack()


    # ---Failure handling---    
    def _exit_if_max_attack_reached(self):
        if self._ka > Ta - Nap:
            log.error("MDLAA exceeded max attack iterations. Stopping...")
            del self.station_ref
            exit(0)


    # ---Logging---
    def _is_MDLAA_successful(self):   
        for freq in self._curr_freqs:
            if freq >= Omega_r_weight:
                log.warning(f"MDLAA SUCCESSFUL: {self._curr_freqs * NOMINAL_FREQ}")
                return True
        return False
    
    def _update_and_log_all_time_max_min_attacks(self):
        for i in range(NUM_ATTACKED_LOAD_BUSES):
            if self._curr_attack[i] > self._all_max_attack[i]:
                self._all_max_attack[i] = self._curr_attack[i]
            elif self._curr_attack[i] < self._all_min_attack[i]:
                self._all_min_attack[i] = self._curr_attack[i]
        log.debug(f"Max attacks: {self._all_max_attack.tolist() * NOMINAL_PS}")
        log.debug(f"Min attacks: {self._all_min_attack.tolist() * NOMINAL_PS}")


def main():
    logs_file = "logs/d_r_lfc_mdlaa.log"
    outstation_ip = "172.24.14.212"
    port = 20001
    outstation_ip2 = "172.24.14.213"
    port2 = 20002
    
    loads_coeffs = np.ones(NUM_ATTACKED_LOAD_BUSES)

    queues_manager = Manager()      
    master_to_osqp = queues_manager.Queue()
    osqp_to_master = queues_manager.Queue()
    
    osqp = Process(target=osqp_process, args=(master_to_osqp, osqp_to_master,), daemon=True)
        
    master = MasterStation(outstation_ip=outstation_ip, port=port, master_id=1, outstation_id=2, log_handler=None)
    soe_handler = MDLAASOEHandler(logs_file, station_ref=master, attacks=loads_coeffs,
                                  master_to_osqp=master_to_osqp, osqp_to_master=osqp_to_master)
    master.configure_master(soe_handler, outstation_ip, port, scan_time=step_time)
    
    master2 = MasterStation(outstation_ip=outstation_ip2, port=port2, master_id=1, outstation_id=2, log_handler=None)
    soe_handler2 = MDLAAHandlerSecondary(logs_file, station_ref=master2, attack=loads_coeffs)
    master2.configure_master(soe_handler2, outstation_ip2, port2, scan_time=step_time)
    
    master.start()
    master2.start()
    osqp.start()
    
    time.sleep(1_000_000_000)
    del master
    del master2
    exit(0)


if __name__ == "__main__":
    main()