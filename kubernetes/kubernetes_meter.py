import argparse
import datetime

from gratia_k8s_config import GratiaK8sConfig
from dirq.QueueSimple import QueueSimple
import os
from datetime import datetime, timezone 
import re

from gratia.common.Gratia import DebugPrint
from gratia.common.debug import DebugPrintTraceback
import gratia.common.GratiaCore as GratiaCore
import gratia.common.GratiaWrapper as GratiaWrapper
import gratia.common.Gratia as Gratia
import gratia.common.config as config

probe_version = "%%%RPMVERSION%%%"

probe_name = os.path.basename(os.path.dirname(os.path.abspath(__file__)))

# log levels
CRITICAL = 0
ERROR    = 1
WARNING  = 2
INFO     = 3
DEBUG    = 4

# Gratia record constants 
SECONDS = "Was entered in seconds"
LOCAL_USER = "osgvo-container-pilot"
USER = "user"
RESOURCE_TYPE = "Batch"

BATCH_SIZE = 100

class ApelRecordConverter():
    apel_dict: dict

    def __init__(self, apel_record: bytes):
        self._parse_apel_str(apel_record.decode())

    def _parse_apel_str(self, apel_record: str):
        self.apel_dict = {}
        lines = apel_record.split('\n')
        for line in lines:
            kv_pair = [v.strip() for v in line.split(':')]
            if len(kv_pair) == 2:
                self.apel_dict[kv_pair[0]] = kv_pair[1]

    def getint(self, key):
        return int(float(self.apel_dict.get(key, 0)))

    def get(self, key):
        return self.apel_dict.get(key)
    

    def site_probe(self):
        site_dns = re.sub(r'[^a-zA-Z0-9-]', '-', self.get('Site')).strip('-')  # sanitize site
        return "kubernetes:%s.gratia.osg-htc.org" % site_dns

    def to_gratia_record(self):
        # TODO the following fields are not currently tracked:
        #      memory, machine name, grid
        r = Gratia.UsageRecord(RESOURCE_TYPE)
        r.StartTime(   self.getint('StartTime'), SECONDS)
        r.MachineName (self.get('MachineName'))
        r.LocalJobId(  self.get('LocalJobId'))
        r.EndTime(     self.getint('EndTime'), SECONDS)
        r.WallDuration(self.getint('WallDuration'), SECONDS)
        r.CpuDuration( self.getint('CpuDuration'), USER, SECONDS)
        r.Memory(      self.getint('MemoryVirtual'), 'KB', description='RSS')
        r.Processors(  self.getint('Processors'), metric="max")
        r.SiteName(    self.get('Site'))
        r.ProbeName(   self.site_probe())
        r.Grid(        self.get('InfrastructureType')) # Best guess
        r.LocalUserId( LOCAL_USER)
        r.VOName(      self.get('VO'))
        r.ReportableVOName(self.get('VO'))
        return r

    @classmethod
    def is_individual_record(cls, data:bytes):
        return data.decode().startswith('APEL-individual-job-message:')


def send_gratia_records(records: list[ApelRecordConverter]):
    # TODO the assumption of uniform site/probe might not be true
    site = records[0].get('Site')
    probe = records[0].site_probe()

    # GratiaCore.Initialize(gratia_config)

    config.Config.setSiteName(site)
    config.Config.setMeterName(probe)

    GratiaCore.Handshake()

    try:
        GratiaCore.SearchOutstandingRecord()
    except Exception as e:
        print(f"Failed to search outstanding records: {e}")
        raise

    GratiaCore.Reprocess()

    for record in records:
        resp = GratiaCore.Send(record.to_gratia_record())
        print(resp)

    GratiaCore.ProcessCurrentBundle()
            



def setup_gratia(config: GratiaK8sConfig):

    print(config.gratia_config_path)
    if not config.gratia_config_path or not os.path.exists(config.gratia_config_path):
        raise Exception("No valid gratia config path given")
    GratiaCore.Config = GratiaCore.ProbeConfiguration(config.gratia_config_path)

    GratiaWrapper.CheckPreconditions()
    GratiaWrapper.ExclusiveLock()

    # Register gratia
    GratiaCore.RegisterReporter("kubernetes_meter")
    GratiaCore.RegisterService("Kubernetes", config.gratia_probe_version)
    GratiaCore.setProbeBatchManager("kubernetes")

    GratiaCore.Initialize(config.gratia_config_path)

def batch_dirq(queue, batch_size):
    """ batch the records in a dirq into groups of a fixed size """
    # TODO this is not the most elegant approach
    records = []
    for name in queue:
        records.append(name)
        if len(records) >= batch_size:
            yield records
            records = []
    # Yield the last entries as well
    yield records

def main(envFile: str):
    print(f'Starting Gratia post-processor: {__file__} with envFile {envFile} at {datetime.now(tz=timezone.utc).isoformat()}')
    cfg = GratiaK8sConfig(envFile)

    setup_gratia(cfg)

    dirq = QueueSimple(str(cfg.output_path))
    for batch in batch_dirq(dirq, BATCH_SIZE):
        apel_records = []
        for name in batch:
            if not dirq.lock(name):
                continue
            data = dirq.get(name)
            if ApelRecordConverter.is_individual_record(data):
                apel_records.append(ApelRecordConverter(data))
            dirq.unlock(name)
        if apel_records:
            send_gratia_records(apel_records)
        # Clear out the chunk of the queue if all the sends succeed
        for name in batch:
            if not dirq.lock(name):
                continue
            dirq.remove(name)
    print("done")

    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract Kubernetes job accounting data from Prometheus and prepare it for APEL publishing.")
    # This should be the only CLI argument, since all other config should be specified via env.
    parser.add_argument("-e", "--env-file", default=None, help="name of file containing environment variables for configuration")
    args = parser.parse_args()
    main(args.env_file)
