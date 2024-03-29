"""
openstack client
"""
import os

from cinderclient import client as cinder_client
import glanceclient
from keystoneauth1.identity import v3
from keystoneauth1.session import Session
from keystoneclient.v3 import client
from neutronclient.v2_0 import client as neutron_client
from novaclient import client as nova_client
from novaclient import exceptions as nova_exc

from easy2use.common import exceptions as base_exc
from easy2use.common import retry
from ectoys.common import log

LOG = log.getLogger()

NOVA_API_VERSION = "2.37"
nova_extensions = [ext for ext in
                   nova_client.discover_extensions(NOVA_API_VERSION)
                   if ext.name in ("assisted_volume_snapshots",
                                   "list_extensions",
                                   "server_external_events")]


class OpenstackClient(object):
    V3_AUTH_KWARGS = ['username', 'password', 'project_name',
                      'user_domain_name', 'project_domain_name',
                      'region_name']

    def __init__(self, *args, **kwargs):
        region_name = kwargs.pop('region_name', None)
        self.auth = v3.Password(*args, **kwargs)
        self.session = Session(auth=self.auth)
        self.keystone = client.Client(session=self.session)
        self.neutron = neutron_client.Client(session=self.session,
                                             region_name=region_name)
        self.nova = nova_client.Client(NOVA_API_VERSION, session=self.session,
                                       extensions=nova_extensions,
                                       region_name=region_name)
        self.glance = glanceclient.Client('2', session=self.session,
                                          region_name=region_name)
        self.cinder = cinder_client.Client('3', session=self.session,
                                           region_name=region_name)

    @classmethod
    def get_auth_info_from_env(cls):
        if 'OS_AUTH_URL' not in os.environ:
            raise base_exc.EnvIsNone('OS_AUTH_URL')
        auth_url = os.getenv('OS_AUTH_URL')
        auth_kwargs = {}
        for auth_arg in cls.V3_AUTH_KWARGS:
            env = f'OS_{auth_arg.upper()}'
            if not os.getenv(env):
                raise base_exc.EnvIsNone(env)
            auth_kwargs[auth_arg] = os.getenv(env)
        return auth_url, auth_kwargs

    @classmethod
    def create_instance(cls):
        auth_url, auth_kwargs = cls.get_auth_info_from_env()
        LOG.debug('auth info: {}', auth_kwargs)
        return OpenstackClient(auth_url, **auth_kwargs)

    def attach_interface(self, net_id=None, port_id=None):
        return self.nova.servers.interface_attach(net_id=net_id,
                                                  port_id=port_id)

    def detach_interface(self, vm_id, port_id):
        return self.nova.servers.interface_detach(vm_id, port_id)

    def list_interface(self, vm_id):
        return self.nova.servers.interface_list(vm_id)

    def attach_volume(self, vm_id, volume_id):
        return self.nova.volumes.create_server_volume(vm_id, volume_id)

    def detach_volume(self, vm_id, volume_id):
        return self.nova.volumes.delete_server_volume(vm_id, volume_id)

    def create_volume(self, name, size_gb=None, image_ref=None,
                      snapshot=None, volume_type=None):
        size = size_gb or 1
        return self.cinder.volumes.create(size, name=name, imageRef=image_ref,
                                          snapshot_id=snapshot,
                                          volume_type=volume_type)

    def get_volume(self, volume_id):
        return self.cinder.volumes.get(volume_id)

    def delete_volume(self, volume_id):
        return self.cinder.volumes.delete(volume_id)

    def get_vm_actions(self, vm):
        actions = {}
        for action in self.nova.instance_action.list(vm.id):
            actions.setdefault(action.action, [])
            vm_action = self.nova.instance_action.get(vm.id,
                                                      action.request_id)
            for event in vm_action.events:
                actions[action.action].append(event)
        return actions

    def get_vm_events(self, vm):
        action_events = []
        for action in self.nova.instance_action.list(vm.id):
            vm_action = self.nova.instance_action.get(vm.id,
                                                      action.request_id)
            events = sorted(vm_action.events,
                            key=lambda x: x.get('start_time'))
            action_events.append((action.action, events))
        return action_events

    def get_server_interfaces(self, server_id):
        return self.nova.servers.interface_list(server_id)

    def detach_server_interface(self, server_id, port_id, wait=False,
                                interval=5, timeout=600):
        self.detach_interface(server_id, port_id)

        if not wait:
            return

        def _check_interface():
            interfaces = self.get_server_interfaces(server_id)
            return all(interface.id != port_id for interface in interfaces)

        LOG.debug('[vm: %s] interface %s detaching', server_id, port_id)
        retry.retry_untile_true(_check_interface,
                                interval=interval, timeout=timeout)
        LOG.debug('[vm: %s] interface %s detached', server_id, port_id)

    def list_volumes(self, all_tenants=False):
        return self.cinder.volumes.list({'all_tenants': all_tenants})

    def get_flavor(self, id_or_name):
        try:
            return self.nova.flavors.get(id_or_name)
        except nova_exc.NotFound:
            return self.nova.flavors.find(name=id_or_name)

def factory():
    return OpenstackClient.create_instance()
