import json
import time
import base64
import time
import logging
import contextlib

import libvirt
import libvirt_qemu

from easy2use.globals import log

LOG = logging.getLogger(__name__)


class DomainNotFound(Exception):
    def __init__(self, name):
        super().__init__(f'Domain {name} not found.')


class Guest(object):

    def __init__(self, host, domain):
        self.host = host
        self.name_or_id = domain
        self._domain = None
        self._connect = None

    @property
    def connect(self):
        if not self._connect:
            self._connect = libvirt.open(f'qemu+tcp://{self.host}/system')
        return self._connect

    def _lookup_domain(self):
        if self._domain:
            return
        for func in [self.connect.lookupByName,
                     self.connect.lookupByUUIDString]:
            try:
                self._domain = func(self.name_or_id)
                break
            except libvirt.libvirtError as e:
                if e.get_error_code() != libvirt.VIR_ERR_NO_DOMAIN:
                    raise

    @property
    def domain(self):
        self._lookup_domain()
        if not self._domain:
            raise DomainNotFound(self.name_or_id)
        return self._domain

    @property
    def uuid(self):
        return self.domain.UUIDString()

    def _get_agent_exec_cmd(self, cmd):
        """
        param: cmd   list or str
        """
        cmd_list = isinstance(cmd, str) and cmd.split() or cmd
        cmd_obj = {'execute': 'guest-exec',
                   'arguments': {'capture-output': True,
                                 'path': cmd_list[0], 'arg': cmd_list[1:]}}
        return json.dumps(cmd_obj)

    def _get_agent_exec_status_cmd(self, pid):
        return json.dumps(
            {'execute': 'guest-exec-status', 'arguments': {'pid': pid}})

    def guest_exec(self, cmd, wait_exists=True, timeout=60):
        exec_cmd = self._get_agent_exec_cmd(cmd)
        result = libvirt_qemu.qemuAgentCommand(self.domain, exec_cmd,
                                               timeout, 0)
        result_obj = json.loads(result)
        cmd_pid = result_obj.get('return', {}).get('pid')
        LOG.debug('[vm: %s] RUN: %s => PID: %s',
                  self.domain.UUIDString(), cmd, cmd_pid)

        if not cmd_pid:
            raise RuntimeError('guest-exec pid is none')
        return (
            self.guest_exec_status(cmd_pid, wait_exists=wait_exists,
                                   timeout=timeout)
            if wait_exists else cmd_pid
        )

    def guest_exec_status(self, pid, wait_exists=False, timeout=None):
        cmd_obj = self._get_agent_exec_status_cmd(pid)
        result_obj = {}
        start_timeout = time.time()
        while True:
            LOG.debug('waiting for %s', pid)
            result = libvirt_qemu.qemuAgentCommand(self.domain, cmd_obj,
                                                   timeout, 0)
            result_obj = json.loads(result)
            if not wait_exists or result_obj.get('return', {}).get('exited'):
                break
            if timeout and (time.time() - start_timeout) >= timeout:
                raise RuntimeError(f'Waiting for {pid} timeout')
            time.sleep(1)
        out_data = result_obj.get('return', {}).get('out-data')
        err_data = result_obj.get('return', {}).get('err-data')
        out_decode = out_data and base64.b64decode(out_data)
        err_decode = err_data and base64.b64decode(err_data)
        LOG.debug('[vm: %s] PID: %s => OUTPUT: %s',
                 self.domain.UUIDString(), pid, out_decode)
        return out_decode or err_decode

    def rpm_i(self, rpm_file):
        if rpm_file:
            self.guest_exec(['/usr/bin/rpm','-ivh', rpm_file])

    def is_ip_exists(self, ipaddress):
        result = self.guest_exec(['/sbin/ip', 'a'])
        return f'inet {ipaddress}/' in result

    def hostname(self):
        return self.guest_exec(['/usr/bin/hostname'])

    def whereis_cmd(self, cmd):
        result = self.guest_exec(['/usr/bin/whereis', cmd])
        return result and result.split()[1] or None

    def kill(self, pid, signal=9):
        self.guest_exec(['/usr/bin/kill', str(signal), str(pid)])

    def start_iperf_server(self, iperf_cmd, logfile):
        return self.guest_exec(
            [iperf_cmd, '--format', 'K', '-s', '--logfile', logfile],
            wait_exists=False)

    def start_iperf_client(self, iperf_cmd, target, timeout=60 * 5):
        return self.guest_exec(
            [iperf_cmd, '--format', 'k', '-c', target],
            wait_exists=True, timeout=timeout)

    @contextlib.contextmanager
    def open_iperf3_server(self, iperf_cmd, logfile):
        server_pid = self.guest_exec(
            [iperf_cmd, '--format', 'k', '-s', '--logfile', logfile],
            wait_exists=False)

        yield server_pid

        self.kill(server_pid)

    def update_device(self, xml, persistent=False, live=False):
        flags = persistent and libvirt.VIR_DOMAIN_AFFECT_CONFIG or 0
        flags |= live and libvirt.VIR_DOMAIN_AFFECT_LIVE or 0

        with open(xml) as f:
            device_xml = ''.join(f.readlines())
            self.domain.updateDeviceFlags(device_xml, flags=flags)
