from pydnp3 import asiodnp3, opendnp3, openpal
from dnp3_python.dnp3station.master import MyMaster


class MasterStation(MyMaster):    
    def configure_master(self, soe_handler, outstation_ip, port, concurrency_hint):
        self.clean_master()
        self.soe_handler = soe_handler
        self.manager = asiodnp3.DNP3Manager(concurrency_hint, self.log_handler)
        self.channel = self.manager.AddTCPClient(id="tcpclient",
                                                 levels=opendnp3.levels.NORMAL,
                                                 retry=self.retry,
                                                 host=outstation_ip,
                                                 local="0.0.0.0",
                                                 port=port,
                                                 listener=self.listener)
        self.master = self.channel.AddMaster(id="master",
                                             SOEHandler=self.soe_handler,
                                             application=self.master_application,
                                             config=self.stack_config)
        self.fast_scan = self.master.AddClassScan(opendnp3.ClassField().AllClasses(),
                                                  openpal.TimeDuration().Seconds(1),
                                                  opendnp3.TaskConfig().Default())

    def clean_master(self):
        del self.soe_handler
        del self.manager
        del self.channel
        del self.master
        del self.fast_scan
        self.slow_scan = ""