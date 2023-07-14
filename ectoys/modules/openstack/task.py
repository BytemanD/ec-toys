from concurrent import futures
import logging
import uuid
import random

from easy2use.globals import cfg
from easy2use.common import retry
from easy2use.common import colorstr
from easy2use.common import table
from easy2use.common import workers as task_workers
from easy2use.component import pbr


from ectoys import utils
from . import manager
from . import exceptions

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class VmActionTest(manager.OpenstackManager):
    flavors = {}

    def create_vm(self, image_id, flavor_id, name=None, nics=None,
                  create_timeout=1800, wait=False):
        nics = nics or self._get_nics()
        if not name:
            name = self.generate_name(
                CONF.openstack.boot_from_volume and 'vol-vm' or 'img-vm')
        image, block_device_mapping_v2 = None, None
        if CONF.openstack.boot_from_volume:
            block_device_mapping_v2 = [{
                'source_type': 'image', 'uuid': image_id,
                'volume_size': CONF.openstack.volume_size,
                'destination_type': 'volume', 'boot_index': 0,
                'delete_on_termination': True,
            }]
        else:
            image = image_id
        vm = self.client.nova.servers.create(
            name, image, flavor_id, nics=nics,
            block_device_mapping_v2=block_device_mapping_v2,
            availability_zone=CONF.openstack.boot_az)
        LOG.info('[vm: %s] booting, with %s', vm.id,
                 'bdm' if block_device_mapping_v2 else 'image')
        if wait:
            try:
                self._wait_for_vm(vm, timeout=create_timeout)
            except exceptions.VMIsError:
                raise exceptions.VmCreatedFailed(vm=vm.id)
            LOG.debug('[vm: %s] created, host is %s',
                      vm.id, getattr(vm, 'OS-EXT-SRV-ATTR:host'))
        return vm

    def _get_flavor_id(self, flavor):
        if not flavor:
            raise exceptions.InvalidConfig(reason='flavor is none')
        flavor_id = None

        try:
            uuid.UUID(flavor)
            flavor_id = flavor
        except (TypeError, ValueError):
            if flavor in self.flavors:
                flavor_id = self.flavors[flavor]
            else:
                flavor_obj = self.client.nova.flavors.find(name=flavor)
                flavor_id = flavor_obj.id
                self.flavors[flavor] = flavor_id
                LOG.info('find flavor id is: %s', flavor_id)

        return flavor_id

    @staticmethod
    def _get_nics():
        return [
            {'net-id': net_id} for net_id in CONF.openstack.net_ids
        ] if CONF.openstack.net_ids else 'none'

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

    def run(self, actions, random_order=False):
        test_actions = random.sample(
            actions, len(actions)) if random_order else actions

        vm = self.create_vm(CONF.openstack.image_id,
                            self._get_flavor_id(CONF.openstack.flavor),
                            nics=self._get_nics())

        LOG.info('[vm: %s] creating', vm.id)
        try:
            self._wait_for_vm(vm, timeout=CONF.boot.timeout)
            if CONF.boot.check_console_log:
                self._wait_for_console_log(vm, interval=10)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            if CONF.task.cleanup_error_vms:
                self.delete_vm(vm)
            raise exceptions.StartFailed(vm=vm.id, reason=e)
        LOG.info(colorstr.GreenStr('[vm: %s] created, host: %s'),
                 vm.id, getattr(vm, 'OS-EXT-SRV-ATTR:host'))

        error = False
        try:
            for action in test_actions:
                getattr(self, f'test_{action}')(vm)
        except Exception as e:
            LOG.exception(e)
            LOG.error(colorstr.RedStr('[vm: %s] test failed, error: %s'),
                      vm.id, e)
            error = True
        else:
            LOG.info(colorstr.GreenStr('[vm: %s] test success'), vm.id)
        finally:
            self.report_vm_actions(vm)
            if not error or CONF.task.cleanup_error_vms:
                self.clean_vms([vm])

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

    def test_stop(self, vm):
        vm.stop()
        LOG.info('[vm: %s] stopping', vm.id)
        try:
            self._wait_for_vm(vm, status='stopped', timeout=60 * 5)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.StopFailed(vm=vm.id, reason=e)
        LOG.info(colorstr.GreenStr('[vm: %s] stopped'), vm.id)
        vm.start()
        LOG.info('[vm: %s] starting', vm.id)
        try:
            vm = self._wait_for_vm(vm, timeout=60 * 5)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.StartFailed(vm=vm.id, reason=e)
        LOG.info(colorstr.GreenStr('[vm: %s] started'), vm.id)
        return vm

    @utils.do_times(options=CONF.reboot)
    def test_reboot(self, vm):
        vm.reboot()
        LOG.info('[vm: %s] rebooting', vm.id)
        try:
            self._wait_for_vm(vm, timeout=60 * 10, interval=5)
            if CONF.boot.check_console_log:
                self._wait_for_console_log(vm, interval=10)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.RebootFailed(vm=vm.id, reason=e)
        LOG.info(colorstr.GreenStr('[vm: %s] rebooted'), vm.id)
        return vm

    def test_hard_reboot(self, vm):
        vm.reboot(reboot_type='HARD')
        LOG.info('[vm: %s] hard rebooting', vm.id)
        try:
            self._wait_for_vm(vm, timeout=60 * 10, interval=5)
            if CONF.boot.check_console_log:
                self._wait_for_console_log(vm, interval=10)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.RebootFailed(vm=vm.id, reason=e)
        LOG.info(colorstr.GreenStr('[vm: %s] heard rebooted'), vm.id)

    def test_suspend(self, vm):
        vm.suspend()
        LOG.info('[vm: %s] suspending', vm.id)
        try:
            self._wait_for_vm(vm, status='suspended', timeout=60 * 5)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.SuspendFailed(vm=vm.id, reason=e)
        LOG.info(colorstr.GreenStr('[vm: %s] suspended'), vm.id)
        vm.resume()
        LOG.info('[vm: %s] resuming', vm.id)
        try:
            self._wait_for_vm(vm, timeout=60 * 5)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.ResumeFailed(vm=vm.id, reason=e)
        LOG.info(colorstr.GreenStr('[vm: %s] resumed'), vm.id)

    def test_pause(self, vm):
        vm.pause()
        LOG.info('[vm: %s] pasuing', vm.id)
        try:
            self._wait_for_vm(vm, status='paused', timeout=60 * 5)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.ResumeFailed(vm=vm.id, reason=e)
        LOG.info(colorstr.GreenStr('[vm: %s] paused'), vm.id)
        vm.unpause()
        LOG.info('[vm: %s] unpasuing', vm.id)
        try:
            self._wait_for_vm(vm, timeout=60 * 5)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.ResumeFailed(vm=vm.id, reason=e)
        LOG.info(colorstr.GreenStr('[vm: %s] unpaused'), vm.id)

    def test_interface_attach_detach(self, vm):
        for index in range(CONF.interface.attach_net_times):
            LOG.info('[vm: %s] test interface attach & detach %s',
                     vm.id, index + 1)

            attached_ports = []
            for i in range(CONF.interface.attach_net_nums):
                LOG.info('[vm: %s] attach interface %s', vm.id, i + 1)
                attached = vm.interface_attach(None, CONF.openstack.attach_net,
                                               None)
                attached_ports.append(attached.port_id)
            ips = self._get_vm_ips(vm.id)
            LOG.info('[vm: %s] ip address are: %s', vm.id, ips)
            self.detach_interfaces_and_wait(vm.id, attached_ports)
            ips = self._get_vm_ips(vm.id)
            LOG.info('[vm: %s] ip address are: %s', vm.id, ips)

    def test_volume_attach(self, vm):
        attached_volumes = []
        for i in range(CONF.task.attach_volume_nums):
            vol = self._create_volume(wait=True)
            LOG.info('[vm: %s] attaching volume %s, %s', vm.id, vol.id, i + 1)
            self._attach_volume(vm, vol.id, wait=True)
            LOG.info('[vm: %s] attached volume %s, %s', vm.id, vol.id, i + 1)
            attached_volumes.append(vol)
        LOG.info(colorstr.GreenStr('[vm: %s] attached %s volume(s)'),
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
        LOG.info('available services num: %s', len(services))
        if not services:
            if host:
                reason = f'Compute service on {host} is not available'
            else:
                reason = 'All compute services are not available'
            raise exceptions.NotAvailableServices(reason=reason)

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
        LOG.debug('[vm: %s] created new flavor, ram=%s vcpus=%s',
                  vm.id, new_flavor.vcpus, new_flavor.ram)
        src_host = getattr(vm, 'OS-EXT-SRV-ATTR:host')
        vm.resize(new_flavor)
        LOG.info('[vm: %s] resizing', vm.id)
        try:
            self._wait_for_vm(vm, timeout=60 * 10, interval=5)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.ResizeFailed(vm=vm.id, reason=e)
        dest_host = getattr(vm, 'OS-EXT-SRV-ATTR:host')
        LOG.info(colorstr.GreenStr('[vm: %s] resized %s -> %s'), vm.id,
                 src_host, dest_host)

    def test_migrate(self, vm):
        if not self.check_can_migrate(vm):
            return
        src_host = getattr(vm, 'OS-EXT-SRV-ATTR:host')
        vm.migrate()
        LOG.info('[vm: %s] cold migrating', vm.id)
        try:
            self._wait_for_vm(vm, timeout=60 * 10, interval=5)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.MigrateFailed(vm=vm.id, reason=e)
        dest_host = getattr(vm, 'OS-EXT-SRV-ATTR:host')
        if src_host == dest_host:
            raise exceptions.MigrateFailed(
                vm=vm.id, reason='src host and dest host are the same')
        LOG.info(colorstr.GreenStr('[vm: %s] migrated, %s --> %s'),
                 vm.id, src_host, dest_host)

    def test_live_migrate(self, vm):
        if not self.check_can_migrate(vm):
            return
        src_host = getattr(vm, 'OS-EXT-SRV-ATTR:host')
        vm.live_migrate()
        LOG.info('[vm: %s] live migrating', vm.id)
        try:
            self._wait_for_vm(vm, timeout=60 * 10, interval=5)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.LiveMigrateFailed(vm=vm.id, reason=e)
        dest_host = getattr(vm, 'OS-EXT-SRV-ATTR:host')
        if src_host == dest_host:
            raise exceptions.LiveMigrateFailed(
                vm=vm.id, reason='src host and dest host are the same')
        LOG.info(colorstr.GreenStr('[vm: %s] live migrated, %s --> %s'),
                 vm.id, src_host, dest_host)

    def test_backup(self, vm):
        vm.backup(self.generate_name('backup'))
        LOG.info('[vm: %s] backup started', vm.id)
        try:
            self._wait_for_vm(vm, timeout=60 * 10, interval=5)
        except (exceptions.WaitVMStatusTimeout, exceptions.VMIsError) as e:
            raise exceptions.VMBackupFailed(vm=vm.id, reason=e)
        LOG.info('[vm: %s] backup success', vm.id)

    def test_volume_detach(self, vm, attached_volumes):
        for vol in attached_volumes:
            LOG.info('[vm: %s] volume %s detaching', vm.id, vol.id)
            self._detach_volume(vm, vol.id, wait=True)
        LOG.info(colorstr.GreenStr('[vm: %s] detached %s volume(s)'),
                 vm.id, len(attached_volumes))

    def test_volume_attach_detach(self, vm):
        attached_volumes = []
        for t in range(CONF.task.attach_volume_times):
            LOG.info('[vm: %s] volume attaching %s', vm.id, t + 1)
            attached_volumes = self.test_volume_attach(vm)
            self.test_volume_detach(vm, attached_volumes)

        vol_devices = self._get_vm_volume_devices(vm)
        LOG.info('[vm: %s] block devices: %s', vm.id, vol_devices)
        LOG.debug('clean up volumes: %s', attached_volumes)
        self.delete_volumes(attached_volumes)

    def _wait_for_console_log(self, vm, interval=10):
    
        def check_vm_console_log():
            output = vm.get_console_output(length=10)
            LOG.debug('[vm: %s] console log: %s', vm.id, output)
            for key in CONF.boot.console_log_error_keys:
                if key not in output:
                    continue
                LOG.error('[vm: %s] found "%s" in conosole log', vm.id, key)
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
        LOG.info('[vm: %s] attaching volume %s', vm.id, vol.id)
        self._attach_volume(vm, vol.id, wait=True)
        LOG.info('[vm: %s] attached volume %s', vm.id, vol.id)
        return vol

    def _attach_volume(self, vm, volume_id, wait=False, check_with_qga=False):
        self.client.attach_volume(vm.id, volume_id)
        LOG.info('[vm: %s] attaching volume %s', vm.id, volume_id)
        if not wait:
            return

        def check_volume():
            vol = self.client.cinder.volumes.get(volume_id)
            LOG.debug('[vm: %s] volume %s status: %s',
                     vm.id, volume_id, vol.status)
            if vol.status == 'error':
                raise exceptions.VolumeDetachFailed(volume=volume_id)
            return vol.status == 'in-use'

        retry.retry_untile_true(check_volume, interval=5, timeout=600)
        if check_with_qga:
            # qga = guest.QGAExecutor()
            # TODO: check with qga
            pass
            LOG.warning('[vm: %s] TODO check with qga')
        LOG.info('[vm: %s] attached volume %s', vm.id, volume_id)

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
        LOG.info('[vm: %s] volume %s detached', vm.id, volume_id)

    def report_vm_actions(self, vm):
        st = table.SimpleTable()
        vm_actions = self.client.get_vm_events(vm)
        vm_actions = sorted(vm_actions, key=lambda x: x[1][0]['start_time'])
        st.set_header([
            'VM', 'Action', 'Event', 'StartTime', 'EndTime', 'Result'])
        for action_name, events in vm_actions:
            for event in events:
                st.add_row([vm.id, action_name, event['event'],
                            event['start_time'], event['finish_time'],
                            event['result']])
        LOG.info('[vm: %s] actions:\n%s', vm.id, st.dumps())


def coroutine_test_vm():
    test_task = VmActionTest()
    test_task.check_actions()
    test_task.check_services()
    test_task.check_flavor()
    test_task.check_image()

    LOG.info('Start tasks, worker: %s, total: %s, actions: %s',
             CONF.task.worker, CONF.task.total, CONF.task.test_actions)

    failed = 0
    bar = pbr.factory(CONF.task.total, driver='logging')
    with futures.ThreadPoolExecutor(max_workers=CONF.task.worker) as tp:
        tasks = [tp.submit(test_task.run, CONF.task.test_actions)
                 for _ in range(CONF.task.total)]
        for future in futures.as_completed(tasks):
            try:
                future.result()
            except Exception as e:
                failed += 1
                LOG.exception(e)
            finally:
                bar.update(1)

    LOG.info('Summary: total: %s, ' +
             str(colorstr.GreenStr('success: %s')) + ", " +
             str(colorstr.RedStr('failed: %s')) + ".",
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

    LOG.info('Start task, worker: %s, total: %s, actions: %s',
             CONF.task.worker, CONF.task.total, CONF.task.test_actions)

    bar = pbr.factory(CONF.task.total, driver='logging')
    failed = 0
    for result in utils.run_processes(do_test_vm,
                                      nums=CONF.task.total,
                                      max_workers=CONF.task.worker):
        bar.update(1)
        if isinstance(result, Exception):
            failed += 1
            LOG.exception(result)
    return failed
