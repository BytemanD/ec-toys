import logging
import os

from easy2use.globals import cfg

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

default_opts = [
    cfg.BooleanOption('debug', default=False),
    cfg.Option('log_to', default=None),
]

openstack_opts = [
    cfg.Option('env'),
    cfg.Option('image_id'),
    cfg.Option('flavor'),
    cfg.ListOption('net_ids'),
    cfg.Option('attach_net'),
    cfg.BooleanOption('boot_from_volume', default=False),
    cfg.IntOption('volume_size', default=10),
    cfg.Option('boot_az'),
]

task_opts = [
    cfg.Option('worker_type', default='coroutine'),
    cfg.IntOption('total', default=1),
    cfg.IntOption('worker', default=1),
    cfg.BooleanOption('attach_net', default=False),
    cfg.ListOption('test_actions'),

    cfg.IntOption('attach_volume_nums', default=1),
    cfg.IntOption('attach_volume_times', default=1),

    cfg.IntOption('attach_port_nums', default=1),
    cfg.IntOption('attach_port_times', default=1),

    cfg.IntOption('boot_wait_interval', default=1),
    cfg.IntOption('boot_wait_timeout', default=600),

    cfg.IntOption('detach_interface_wait_interval', default=1),
    cfg.IntOption('detach_interface_wait_timeout', default=60),

    cfg.IntOption('migrate_wait_interval', default=5),
    cfg.IntOption('migrate_wait_timeout', default=60),
    cfg.BooleanOption('cleanup_error_vms', default=True),
    cfg.BooleanOption('random_order', default=False),

]

boot_opts = [
     cfg.IntOption('timeout', default=60 * 30),
     cfg.BooleanOption('check_console_log', default=False),
     cfg.IntOption('console_log_timeout', default=600),
     cfg.ListOption('console_log_ok_keys', default=[' login:']),
     cfg.ListOption('console_log_error_keys', default=[]),
]

reboot_opts = [
     cfg.IntOption('times', default=1),
     cfg.IntOption('interval', default=10),
]

hard_reboot_opts = [
     cfg.IntOption('times', default=1),
     cfg.IntOption('interval', default=10),
]

interface_opts = [
    cfg.IntOption('attach_net_nums', default=1),
    cfg.IntOption('attach_net_times', default=1),
]


def load_configs(conf_files):
    for file in conf_files:
        if not os.path.exists(file):
            continue
        LOG.debug('Load config file from %s', file)
        CONF.load(file)
        break
    else:
        LOG.warning('config file not found')


CONF.register_opts(default_opts)
CONF.register_opts(openstack_opts, group='openstack')
CONF.register_opts(task_opts, group='task')
CONF.register_opts(boot_opts, group='boot')
CONF.register_opts(reboot_opts, group='reboot')
CONF.register_opts(hard_reboot_opts, group='hard_reboot')
CONF.register_opts(interface_opts, group='interface')
