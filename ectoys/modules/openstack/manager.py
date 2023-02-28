from concurrent import futures
import logging
import random

from novaclient import exceptions as nova_exc

from easy2use.common import retry
from easy2use.component import pbr
from easy2use import date

from . import client
from . import exceptions


LOG = logging.getLogger(__name__)


def get_vm_state(vm, refresh=False):
    if refresh:
        vm.get()
    return getattr(vm, 'OS-EXT-STS:vm_state')


def create_random_str(length):
    return ''.join(
        random.sample(
            'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789',
            length)
    )


class OpenstackManager:
    
    def __init__(self):
        self.client = client.factory()
        self.flavors_cached = {}

    @staticmethod
    def generate_name(resource):
        return 'ec-utils-{}-{}'.format(
            resource, date.now_str(date_fmt='%m%d-%H:%M:%S'))

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

    def create_volumes(self, size, name=None, num=1, workers=None, image=None,
                       snapshot=None, volume_type=None):
        name = name or self.generate_name(create_random_str(5))
        workers = workers or num
        LOG.info('Try to create %s volume(s), name: %s, image: %s, '
                 'snapshot: %s, workers: %s ',
                 num, name, image, snapshot, workers)
        bar = pbr.factory(num, description='create volumes')
        with futures.ThreadPoolExecutor(max_workers=workers) as executor:
            tasks = [
                executor.submit(self._create_volume,
                                size_gb=size, name=f'{name}-{index}',
                                image=image, snapshot=snapshot,
                                volume_type=volume_type,
                                wait=True,
                )
                for index in range(1, num + 1)
            ]
            volume_ids = []
            LOG.info('Creating, please be patient ...')
            for task in futures.as_completed(tasks):
                bar.update(1)
                vol = task.result()
                if not vol:
                    continue
                LOG.debug('created new volume: %s(%s)', vol.name, vol.id)
                volume_ids.append(vol.id)

            bar.close()
        return volume_ids

    def _create_volume(self, size_gb=None, name=None, image=None,
                       snapshot=None, wait=False, interval=1,
                       volume_type=None):

        def compute_volume_finished(result):
            LOG.debug('volume %s status: %s', result.id, result.status)
            if result.status == 'error':
                LOG.error('volume %s created failed', result.id)
                return exceptions.VolumeCreateTimeout(volume=result.id,
                                                      timeout=timeout)
            return result.status == 'available'

        name = name or self.generate_name('vol')
        LOG.debug('creating volume %s, image=%s, snapshot=%s',
                  name, image, snapshot)
        try:
            vol = self.client.create_volume(name, size_gb=size_gb,
                                            image_ref=image, snapshot=snapshot,
                                            volume_type=volume_type)
        except Exception as e:
            LOG.error(e)
            raise

        if wait:
            # TODO: add timeout argument
            timeout = 600

            retry.retry_for(self.client.get_volume, args=(vol.id,),
                            interval=interval, timeout=timeout,
                            finish_func=compute_volume_finished)

        return vol
