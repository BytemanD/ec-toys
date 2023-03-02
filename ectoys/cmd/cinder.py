import logging

from easy2use.globals import cli


from ectoys.cmd import IntArg
from ectoys.cmd import log_arg_group
from ectoys.modules.openstack import exceptions
from ectoys.modules.openstack import manager

LOG = logging.getLogger(__name__)

parser = cli.SubCliParser('EC Cinder Utils')


@parser.add_command(
    cli.Arg('size', type=int),
    cli.Arg('-n', '--name', help='Volume name. Defaults to a random string'),
    cli.Arg('-i', '--image', help='Image id'),
    cli.Arg('-t', '--type', help='Volume type'),
    IntArg('-w',  '--workers', help='Defaults to use the same value as num'),
    log_arg_group)
def create_volume(args):
    '''Cleanup vm
    '''
    if args.image and args.snapshot:
        raise exceptions.InvalidArgs(
            reason='--image and --snapshot can not specify both')

    mgr = manager.OpenstackManager()
    volumes = mgr.create_volumes(args.size, args.name, num=args.num,
                                 image=args.image, snapshot=args.snapshot,
                                 volume_type=args.vol_type,
                                 workers=args.workers)
    print('new volumes:')
    print("\n".join(volumes))


def main():
    parser.call()


if __name__ == '__main__':
    main()
