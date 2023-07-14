import logging
import pathlib

from easy2use.globals import cli
from easy2use.globals import log

from ectoys.cmd import IntArg
from ectoys.cmd import BoolArg
from ectoys.cmd import log_arg_group
from ectoys.common import conf
from ectoys.modules.openstack import manager
from ectoys.modules.openstack import task
from ectoys import utils

LOG = logging.getLogger(__name__)
CONF = conf.CONF

parser = cli.SubCliParser('EC Nova Utils')


@parser.add_command(
    cli.Arg('--host', help='VM host'),
    cli.Arg('-n', '--name', help='Volume name. Defaults to a random string'),
    cli.Arg('-s', '--status', help='VM status'),
    BoolArg('-f', '--force', help='Force delete'),
    IntArg('-w',  '--workers', help='Defaults to use the same value as num'),
    log_arg_group)
def cleanup_vm(args):
    """Cleanup vm
    """
    if all([not args.name, not args.host, not args.status]):
        no = {'n', 'no'}
        valid_input = no.union({'y', 'yes'})
        sure = input('Are you sure to cleanup all vms (y/n):')
        while sure not in valid_input:
            sure = input('Please input (y/n):')
        if sure in no:
            return

    mgr = manager.OpenstackManager()
    mgr.delete_vms(name=args.name, host=args.host, status=args.status,
                   workers=args.workers, force=args.force)


@parser.add_command(
    cli.Arg('server', help='Server Id'),
    cli.Arg('network', help='Network id'),
    IntArg('-n', '--num', default=1, help='VM status'),
    log_arg_group)
def attach_interface(args):
    """Attach inerface
    """
    mgr = manager.OpenstackManager()
    mgr.attach_interfaces(args.server, args.network, num=args.num)


@parser.add_command(
    cli.Arg('server', help='Server Id'),
    IntArg('--start', default=1, help='Start index of vm interfaces'),
    IntArg('-e', '--end', help='End index of vm interfaces'),
    log_arg_group)
def detach_interface(args):
    """Detach inerface
    """
    mgr = manager.OpenstackManager()
    mgr.detach_interfaces(args.server, start=args.start-1, end=args.end)


@parser.add_command(cli.Arg('-c', '--conf', help='Config file'),
                    log.get_args()[0])
def test_vm(args):
    """Test VM
    """
    LOG.debug('start to test vm')
    if args.conf:
        conf.load_configs([args.conf])
    else:
        conf.load_configs(['/etc/ectoys/ec-nova.conf',
                           pathlib.Path('etc', 'ec-nova.conf').absolute()])
    if CONF.openstack.env and pathlib.Path(CONF.openstack.env).is_file():
        utils.load_env(CONF.openstack.env)

    if CONF.task.worker_type == 'process':
        task.process_test_vm()
    elif CONF.task.worker_type == 'coroutine':
        try:
            task.coroutine_test_vm()
        except Exception as e:
            logging.error("测试失败, %s", e)
    else:
        raise ValueError('Invalid config worker_mode')



def main():
    parser.call()


if __name__ == '__main__':
    main()
