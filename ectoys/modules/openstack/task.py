from concurrent import futures
import random

from easy2use.globals import cfg
from easy2use.common import retry
from easy2use.common import colorstr
from easy2use.common import table
from easy2use.component import pbr


from ectoys.common import log
from ectoys.common import utils
from . import manager
from ...common import exceptions


CONF = cfg.CONF
LOG = log.getLogger()


class VmActionTest(manager.OpenstackManager):
    flavors = {}

    def _get_flavor(self, flavor_id):
        if flavor_id not in self.flavors_cached:
            self.flavors_cached[flavor_id] = self.client.nova.flavors.get(
                self._get_flavor_id(CONF.openstack.flavor))
        return self.flavors_cached[flavor_id]

    def detach_interfaces_and_wait(self, vm_id, port_ids):
        self.detach_interfaces(vm_id, port_ids=port_ids)

        def check_interfaces():
            interfaces = self.client.nova.servers.interface_list(vm_id)
            return all(vif.id not in port_ids for vif in interfaces)

        retry.retry_untile_true(
            check_interfaces,
            interval=CONF.task.detach_interface_wait_interval,
            timeout=CONF.task.detach_interface_wait_timeout)

    def create_flavor(self, ram, vcpus, disk=0, metadata=None):
        return self.client.create_flavor(self.generate_name('flavor'),
                                         ram, vcpus, disk, metadata=metadata)

    def _info(self, msg, *args):
        LOG.info("[vm: {}]" + msg,  *args)

    def _debug(self, msg, *args):
        LOG.debug("[vm: {}]" + msg, *args)

    def _error(self, msg, *args):
        LOG.error("[vm: {}]" + msg, *args)


    def run(self, actions, random_order=False):
        test_actions = random.sample(
            actions, len(actions)) if random_order else actions

        error = False
        vm = None
        try:
            vm = self.create_vm(CONF.openstack.image_id,
                                self._get_flavor_id(CONF.openstack.flavor),
                                nics=self._get_nics())
            LOG.info('[vm: {}] creating', vm.id)

            self._wait_for_vm(vm, timeout=CONF.boot.timeout)
            if CONF.boot.check_console_log:
                self._wait_for_console_log(vm, interval=10)
            LOG.info('[vm: {}] created, host: {}', vm.id, getattr(vm, 'OS-EXT-SRV-ATTR:host'))

            for action in test_actions:
                getattr(self, f'test_{action}')(vm)
        except Exception as e:
            LOG.exception('test failed')
            error = True
            raise e
        else:
            LOG.info('[vm: {}] test success', vm.id)
        finally:
            if vm:
                self.report_vm_actions(vm)
                if not error or CONF.task.cleanup_error_vms:
                    self.delete_vm(vm)

    def _get_vm_volume_devices(self, vm):
        return [
            vol.device for vol in
            self.client.nova.volumes.get_server_volumes(vm.id)
        ]

    def _get_vm_ips(self, vm_id):
        ip_list = []
        for vif in self.client.list_interface(vm_id):
            ip_list.extend([ip['ip_address'] for ip in vif.fixed_ips])
        return ip_list

    # @utils.do_times(options=CONF.reboot)
    # def test_reboot(self, vm):
    #     vm.reboot()
    #     LOG.info('[vm: {}] rebooting', vm.id)
    #     try:
    #         self._wait_for_vm(vm, timeout=60 * 10, interval=5)
    #         if CONF.boot.check_console_log:
    #             self._wait_for_console_log(vm, interval=10)
    #     except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
    #         raise exceptions.RebootFailed(vm=vm.id, reason=e)
    #     LOG.info(colorstr.GreenStr('[vm: {}] rebooted'), vm.id)
    #     return vm

    def test_hard_reboot(self, vm):
        vm.reboot(reboot_type='HARD')
        LOG.info('[vm: {}] hard rebooting', vm.id)
        try:
            self._wait_for_vm(vm, timeout=60 * 10, interval=5)
            if CONF.boot.check_console_log:
                self._wait_for_console_log(vm, interval=10)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.RebootFailed(vm=vm.id, reason=e)
        LOG.info(colorstr.GreenStr('[vm: {}] heard rebooted'), vm.id)

    def test_suspend(self, vm):
        vm.suspend()
        LOG.info('[vm: {}] suspending', vm.id)
        try:
            self._wait_for_vm(vm, status='suspended', timeout=60 * 5)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.SuspendFailed(vm=vm.id, reason=e)
        LOG.info(colorstr.GreenStr('[vm: {}] suspended'), vm.id)
        vm.resume()
        LOG.info('[vm: {}] resuming', vm.id)
        try:
            self._wait_for_vm(vm, timeout=60 * 5)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.ResumeFailed(vm=vm.id, reason=e)
        LOG.info(colorstr.GreenStr('[vm: {}] resumed'), vm.id)

    def test_pause(self, vm):
        vm.pause()
        LOG.info('[vm: {}] pasuing', vm.id)
        try:
            self._wait_for_vm(vm, status='paused', timeout=60 * 5)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.ResumeFailed(vm=vm.id, reason=e)
        LOG.info(colorstr.GreenStr('[vm: {}] paused'), vm.id)
        vm.unpause()
        LOG.info('[vm: {}] unpasuing', vm.id)
        try:
            self._wait_for_vm(vm, timeout=60 * 5)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.ResumeFailed(vm=vm.id, reason=e)
        LOG.info(colorstr.GreenStr('[vm: {}] unpaused'), vm.id)

    def test_interface_attach_detach(self, vm):
        for index in range(CONF.interface.attach_net_times):
            LOG.info('[vm: {}] test interface attach & detach {}',
                     vm.id, index + 1)

            attached_ports = []
            for i in range(CONF.interface.attach_net_nums):
                LOG.info('[vm: {}] attach interface {}', vm.id, i + 1)
                attached = vm.interface_attach(None, CONF.openstack.attach_net,
                                               None)
                attached_ports.append(attached.port_id)
            ips = self._get_vm_ips(vm.id)
            LOG.info('[vm: {}] ip address are: {}', vm.id, ips)
            self.detach_interfaces_and_wait(vm.id, attached_ports)
            ips = self._get_vm_ips(vm.id)
            LOG.info('[vm: {}] ip address are: {}', vm.id, ips)

    def test_volume_attach(self, vm):
        attached_volumes = []
        for i in range(CONF.task.attach_volume_nums):
            vol = self._create_volume(wait=True)
            LOG.info('[vm: {}] attaching volume {}, {}', vm.id, vol.id, i + 1)
            self._attach_volume(vm, vol.id, wait=True)
            LOG.info('[vm: {}] attached volume {}, {}', vm.id, vol.id, i + 1)
            attached_volumes.append(vol)
        LOG.info(colorstr.GreenStr('[vm: {}] attached {} volume(s)'),
                 vm.id, len(attached_volumes))
        return attached_volumes

    def check_actions(self):
        """Make sure configed actions are all exists"""
        for action in CONF.task.test_actions:
            if not hasattr(self, f'test_{action}'):
                return exceptions.VmTestActionNotFound(action=action)

    def check_services(self):
        """Make sure configed actions are all exists"""
        az, host = None, None

        if CONF.openstack.boot_az:
            if ':' in CONF.openstack.boot_az:
                az, host = CONF.openstack.boot_az.split(':')
            else:
                az = CONF.openstack.boot_az

        services = self.get_available_services(host=host, zone=az,
                                               binary='nova-compute')
        if not services:
            if host:
                reason = f'compute service on {host} is not available'
            elif az:
                reason = f'there is no available compute service for az "{az}"'
            raise exceptions.NotAvailableServices(reason=reason)
        else:
            LOG.info('available services num is {}', len(services))

    def check_flavor(self):
        """Make sure configed actions are all exists"""
        if not CONF.openstack.flavor:
            return
        self._get_flavor(CONF.openstack.flavor)

    def check_image(self):
        """Make sure configed actions are all exists"""
        if not CONF.openstack.image_id:
            return
        self.client.glance.images.get(CONF.openstack.image_id)

    def test_resize(self, vm):
        flavor = self._get_flavor(CONF.openstack.flavor)
        new_flavor = self.create_flavor(flavor.ram + 1024, flavor.vcpus + 1,
                                        disk=flavor.disk,
                                        metadata=flavor.get_keys())
        LOG.debug('[vm: {}] created new flavor, ram={} vcpus={}',
                  vm.id, new_flavor.vcpus, new_flavor.ram)
        src_host = getattr(vm, 'OS-EXT-SRV-ATTR:host')
        vm.resize(new_flavor)
        LOG.info('[vm: {}] resizing', vm.id)
        try:
            self._wait_for_vm(vm, timeout=60 * 10, interval=5)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.ResizeFailed(vm=vm.id, reason=e)
        dest_host = getattr(vm, 'OS-EXT-SRV-ATTR:host')
        LOG.info(colorstr.GreenStr('[vm: {}] resized {} -> {}'), vm.id,
                 src_host, dest_host)

    def test_migrate(self, vm):
        if not self.check_can_migrate(vm):
            return
        src_host = getattr(vm, 'OS-EXT-SRV-ATTR:host')
        vm.migrate()
        LOG.info('[vm: {}] cold migrating', vm.id)
        try:
            self._wait_for_vm(vm, timeout=60 * 10, interval=5)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.MigrateFailed(vm=vm.id, reason=e)
        dest_host = getattr(vm, 'OS-EXT-SRV-ATTR:host')
        if src_host == dest_host:
            raise exceptions.MigrateFailed(
                vm=vm.id, reason='src host and dest host are the same')
        LOG.info(colorstr.GreenStr('[vm: {}] migrated, {} --> {}'),
                 vm.id, src_host, dest_host)

    def test_live_migrate(self, vm):
        if not self.check_can_migrate(vm):
            return
        src_host = getattr(vm, 'OS-EXT-SRV-ATTR:host')
        vm.live_migrate()
        LOG.info('[vm: {}] live migrating', vm.id)
        try:
            self._wait_for_vm(vm, timeout=60 * 10, interval=5)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.LiveMigrateFailed(vm=vm.id, reason=e)
        dest_host = getattr(vm, 'OS-EXT-SRV-ATTR:host')
        if src_host == dest_host:
            raise exceptions.LiveMigrateFailed(
                vm=vm.id, reason='src host and dest host are the same')
        LOG.info(colorstr.GreenStr('[vm: {}] live migrated, {} --> {}'),
                 vm.id, src_host, dest_host)

    def test_backup(self, vm):
        vm.backup(self.generate_name('backup'))
        LOG.info('[vm: {}] backup started', vm.id)
        try:
            self._wait_for_vm(vm, timeout=60 * 10, interval=5)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.VMBackupFailed(vm=vm.id, reason=e)
        LOG.info('[vm: {}] backup success', vm.id)

    def test_volume_detach(self, vm, attached_volumes):
        for vol in attached_volumes:
            LOG.info('[vm: {}] volume {} detaching', vm.id, vol.id)
            self._detach_volume(vm, vol.id, wait=True)
        LOG.info(colorstr.GreenStr('[vm: {}] detached {} volume(s)'),
                 vm.id, len(attached_volumes))

    def test_volume_attach_detach(self, vm):
        attached_volumes = []
        for t in range(CONF.task.attach_volume_times):
            LOG.info('[vm: {}] volume attaching {}', vm.id, t + 1)
            attached_volumes = self.test_volume_attach(vm)
            self.test_volume_detach(vm, attached_volumes)

        vol_devices = self._get_vm_volume_devices(vm)
        LOG.info('[vm: {}] block devices: {}', vm.id, vol_devices)
        LOG.debug('clean up volumes: {}', attached_volumes)
        self.delete_volumes(attached_volumes)

    def _wait_for_console_log(self, vm, interval=10):
    
        def check_vm_console_log():
            output = vm.get_console_output(length=10)
            LOG.debug('[vm: {}] console log: {}', vm.id, output)
            for key in CONF.boot.console_log_error_keys:
                if key not in output:
                    continue
                LOG.error('[vm: {}] found "{}" in conosole log', vm.id, key)
                raise exceptions.BootFailed(vm=vm.id)

            match_ok = sum(
                key in output for key in CONF.boot.console_log_ok_keys
            )
            if match_ok == len(CONF.boot.console_log_ok_keys):
                return True

        retry.retry_untile_true(check_vm_console_log, interval=interval,
                                timeout=600)

    def attach_new_volume(self, vm):
        vol = self._create_volume(size_gb=10, wait=True)
        LOG.info('[vm: {}] attaching volume {}', vm.id, vol.id)
        self._attach_volume(vm, vol.id, wait=True)
        LOG.info('[vm: {}] attached volume {}', vm.id, vol.id)
        return vol

    def _attach_volume(self, vm, volume_id, wait=False, check_with_qga=False):
        self.client.attach_volume(vm.id, volume_id)
        LOG.info('[vm: {}] attaching volume {}', vm.id, volume_id)
        if not wait:
            return

        def check_volume():
            vol = self.client.cinder.volumes.get(volume_id)
            LOG.debug('[vm: {}] volume {} status: {}',
                     vm.id, volume_id, vol.status)
            if vol.status == 'error':
                raise exceptions.VolumeDetachFailed(volume=volume_id)
            return vol.status == 'in-use'

        retry.retry_untile_true(check_volume, interval=5, timeout=600)
        if check_with_qga:
            # qga = guest.QGAExecutor()
            # TODO: check with qga
            pass
            LOG.warning('[vm: {}] TODO check with qga')
        LOG.info('[vm: {}] attached volume {}', vm.id, volume_id)

    def _detach_volume(self, vm, volume_id, wait=False):
        self.client.detach_volume(vm.id, volume_id)
        if not wait:
            return

        def check_volume():
            vol = self.client.cinder.volumes.get(volume_id)
            if vol.status == 'error':
                raise exceptions.VolumeDetachFailed(volume=volume_id)
            return vol.status == 'available'

        retry.retry_untile_true(check_volume, interval=5, timeout=600)
        LOG.info('[vm: {}] volume {} detached', vm.id, volume_id)


def coroutine_test_vm():
    test_task = VmActionTest()
    test_task.check_actions()
    test_task.check_services()
    test_task.check_flavor()
    test_task.check_image()

    LOG.info('Start tasks, worker: {}, total: {}, actions: {}',
             CONF.task.worker, CONF.task.total, CONF.task.test_actions)

    failed = 0
    completed = 0
    with futures.ThreadPoolExecutor(max_workers=CONF.task.worker) as tp:
        tasks = [tp.submit(test_task.run, CONF.task.test_actions)
                 for _ in range(CONF.task.total)]
        for future in futures.as_completed(tasks):
            try:
                future.result()
                completed += 1
            except Exception as e:
                failed += 1
                LOG.exception(e)
            finally:
                LOG.info('completed {}/{}', completed, len(tasks))

    LOG.info('Summary: total: {}, ' +
             str(colorstr.GreenStr('success: {}')) + ", " +
             str(colorstr.RedStr('failed: {}')) + ".",
             CONF.task.total, CONF.task.total - failed, failed)


def do_test_vm():
    test_task = VmActionTest()
    return test_task.run(CONF.task.test_actions)


def process_test_vm():
    test_task = VmActionTest()
    test_task.check_actions()
    test_task.check_services()
    test_task.check_flavor()
    test_task.check_image()

    LOG.info('Start task, worker: {}, total: {}, actions: {}',
             CONF.task.worker, CONF.task.total, CONF.task.test_actions)

    failed = 0
    completed = 0
    for result in utils.run_processes(do_test_vm,
                                      nums=CONF.task.total,
                                      max_workers=CONF.task.worker):
        completed += 1 
        if isinstance(result, Exception):
            failed += 1
            LOG.exception(result)
        LOG.info('completed {}/{}', completed, CONF.task.total)
    return failed
