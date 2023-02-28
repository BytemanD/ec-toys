import logging
from concurrent import futures

from novaclient import exceptions as nova_exc

from easy2use.common import retry
from easy2use.component import pbr


from . import client
from . import exceptions


LOG = logging.getLogger(__name__)


def get_vm_state(vm, refresh=False):
    if refresh:
        vm.get()
    return getattr(vm, 'OS-EXT-STS:vm_state')


class OpenstackManager:
    
    def __init__(self):
        self.client = client.factory()
        self.flavors_cached = {}

    def get_task_state(self, vm, refresh=False):
        if refresh:
            vm = self.client.nova.servers.get(vm.id)
        return getattr(vm, 'OS-EXT-STS:task_state')

    def find_servers(self, name=None, status=None, host=None,
                     all_tenants=False):
        LOG.debug('find servers with name=%s, status=%s, host=%s'
                  'all_tenants=%s', name, status, host, all_tenants)
        vms = []
        search_opts = {}
        if all_tenants:
            search_opts['all_tenants'] = 1
        for vm in self.client.nova.servers.list(search_opts=search_opts):
            vm_state = get_vm_state(vm)
            LOG.debug('[vm: %s] name=%s, vm_state=%s',
                      vm.id, vm.name, vm_state)
            if name and (name not in vm.name) or \
               status and vm_state != status or\
               host and getattr(vm, 'OS-EXT-SRV-ATTR:host') != host:
                continue
            vms.append(vm)
        return vms

    def _wait_for_vm(self, vm, status=None, task_states=None, timeout=None,
                     interval=5):
        if not status:
            states = {'active'}
        elif isinstance(status, str):
            states = {status}
        else:
            states = status
        task_states = task_states or [None]

        def check_vm_status():
            vm.get()
            vm_state = get_vm_state(vm)
            if vm_state == 'error':
                raise exceptions.VMIsError(vm=vm.id)
            task_state = self.get_task_state(vm)
            LOG.debug('[vm: %s] vm_state=%s, stask_state=%s',
                      vm.id, vm_state, task_state)
            return vm_state in states and task_state in task_states

        retry.retry_untile_true(check_vm_status,
                                interval=interval, timeout=timeout)

        return vm

    def delete_vm(self, vm, wait=True):
        try:
            vm.delete()
            LOG.debug('[vm: %s] deleting', vm.id)
            if wait:
                self._wait_for_vm(vm, status='deleted')
        except nova_exc.NotFound:
            LOG.debug('[vm: %s] deleted', vm.id)
        return vm

    def delete_vms(self, name=None, host=None, status=None, all_tenants=False,
                   workers=None, ):
        workers = workers or 1
        servers = self.find_servers(name=name, status=status,host=host,
                                             all_tenants=all_tenants)
        LOG.info('found %s deletable server(s)', len(servers))
        if not servers:
            return

        bar = pbr.factory(len(servers))
        LOG.info('delete %s vms ...', len(servers))
        with futures.ThreadPoolExecutor(max_workers=workers) as executor:
            for _ in executor.map(self.delete_vm, servers):
                bar.update(1)
        bar.close()
