from concurrent import futures
import logging
import random
import subprocess


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
        return 'ecToys-{}-{}'.format(
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

    def delete_vm(self, vm, wait=True, force=False):
        if force and not hasattr(vm, 'force_delete'):
            raise Exception('force delete is not support')
        if force:
            vm.force_delete()
        else:
            vm.delete()
        LOG.debug('[vm: %s] deleting', vm.id)
        if wait:
            try:
                self._wait_for_vm(vm, status='deleted')
            except nova_exc.NotFound:
                LOG.debug('[vm: %s] deleted', vm.id)
        return vm

    def _wait_for_volume_deleted(self, vol, timeout=None, interval=5):

        def is_volume_not_found():
            try:
                self.client.cinder.volumes.get(vol.id)
            except Exception as e:
                LOG.debug(e)
                return True

        retry.retry_untile_true(is_volume_not_found,
                                interval=interval, timeout=timeout)

    def delete_vms(self, name=None, host=None, status=None, all_tenants=False,
                   workers=None, force=False):
        workers = workers or 1
        servers = self.find_servers(name=name, status=status, host=host,
                                    all_tenants=all_tenants)
        LOG.info('found %s deletable server(s)', len(servers))
        if not servers:
            return

        with futures.ThreadPoolExecutor(max_workers=workers) as executor:
            tasks = [executor.submit(self.delete_vm, vm, force=force)
                    for vm in servers]

            with pbr.progressbar(len(servers), description='delete vm') as bar:
                for _ in futures.as_completed(tasks):
                    bar.update(1)
        bar.close()

    def create_volumes(self, size, name=None, num=1, workers=None, image=None,
                       snapshot=None, volume_type=None, pbr_driver=None):
        name = name or self.generate_name('vol')
        workers = workers or num
        LOG.info('Try to create %s volume(s), name: %s, image: %s, '
                 'snapshot: %s, workers: %s ',
                 num, name, image, snapshot, workers)
        bar = pbr.factory(num, description='create volumes',
                          driver=pbr_driver or 'logging')
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

    def attach_interfaces(self, server_id, net_id, num=1):
        vm = self.client.nova.servers.get(server_id)
        bar = pbr.factory(num, description='attach interfaces')
        for _ in range(num):
            vm.interface_attach(None, net_id, None)
            bar.update(1)
        bar.close()

    def detach_interfaces(self, server_id, port_ids=None, start=0, end=None):
        if not port_ids:
            port_ids = [
                vif.id for vif in self.client.get_server_interfaces(server_id)
            ]
        port_ids = port_ids[start:(end or len(port_ids))]
        LOG.info('[vm: %s] detach interfaces: %s', server_id, port_ids)
        if not port_ids:
            return
        bar = pbr.factory(len(port_ids), description='detach interface',)
        for port_id in port_ids:
            self.client.detach_server_interface(server_id, port_id, wait=True)
            bar.update(1)
        bar.close()

    def delete_volumes(self, volumes, workers=None):
        LOG.debug('Try to delete %s volumes(s)', len(volumes))
        bar = pbr.factory(len(volumes), driver='logging')
        with futures.ThreadPoolExecutor(max_workers=workers or 1) as executor:
            tasks = [executor.submit(self.delete_volume, vol,
                                     wait=True) for vol in volumes]
            LOG.info('Deleting, please be patient ...')
            for _ in futures.as_completed(tasks):
                bar.update(1)
            bar.close()

    def delete_volume(self, volume, wait=False):
        LOG.debug('delete volume %s', volume.id)
        self.client.delete_volume(volume.id)
        if not wait:
            return
        self._wait_for_volume_deleted(volume, timeout=60)

    def rbd_ls(self, pool):
        status, lines = subprocess.getstatusoutput(f'rbd ls {pool}')
        if status != 0:
            raise RuntimeError(f'Run rbd ls failed, {lines}')
        return lines.split('\n')

    def rbd_rm(self, pool, image):
        cmd = f'rbd remove {pool}/{image}'
        status, output = subprocess.getstatusoutput(cmd)
        if status != 0:
            raise RuntimeError(f'Run rbd rm failed, {output}')

    def cleanup_rbd(self, pool, workers=1):
        volumes = [
            'volume-{}'.format(vol.id) for vol in self.client.list_volumes()]
        lines = self.rbd_ls(pool)
        delete_images = [
            line for line in lines \
                if line and line.startswith('volume') and line not in volumes]
        LOG.info('Found %s image(s)', len(delete_images))
        if not delete_images:
            return
        LOG.info('Try to delete %s image(s) with rbd', len(delete_images))

        def delete_image(image):
            return self.rbd_rm(pool, image)

        bar = pbr.factory(len(delete_images), driver='logging')
        with futures.ThreadPoolExecutor(max_workers=workers or 1) as executor:
            LOG.info('Deleting, please be patient ...')
            for _ in executor.map(delete_image, delete_images):
                bar.update(1)
            bar.close()
