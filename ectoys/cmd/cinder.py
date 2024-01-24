from concurrent import futures

from easy2use.component import pbr
from easy2use.globals import cli

from ectoys.cmd import IntArg
from ectoys.cmd import BoolArg
from ectoys.cmd import log_arg_group
from ectoys.common import exceptions
from ectoys.managers.openstack import manager
from ectoys.common import utils

from ectoys.common import log



parser = cli.SubCliParser('EC Cinder Utils')


@parser.add_command(
    cli.Arg('size', type=int),
    cli.Arg('-n', '--name', help='Volume name. Defaults to a random string'),
    cli.Arg('-i', '--image', help='Image id'),
    cli.Arg('-s', '--snapshot', help='Snapshot id'),
    cli.Arg('-t', '--type', help='Volume type'),
    IntArg('-N', '--num', default=1, help='Volume nums'),
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
                                 volume_type=args.type,
                                 workers=args.workers)
    utils.echo('new volumes:')
    utils.echo(volumes, list_join='\n')


@parser.add_command(
    cli.Arg('-n', '--name', default='ecToys',
            help='Volume name., Defaults to ecToys'),
    IntArg('-w', '--worker', default=1, help='Workers. Defaults to 1'),
    BoolArg('-a', '--all', action='store_true', help='All tenants'),
    log_arg_group)
def cleanup_volume(args):
    """Cleanup Volume
    """
    mgr = manager.OpenstackManager()
    LOG.debug('Cleanup volume by name: %s', args.name)

    found_volumes = [
        vol for vol in mgr.client.list_volumes(all_tenants=args.all)
        if vol.status == 'available' and (
            (vol.name and vol.name.startswith(args.name))
        )
    ]
    if not found_volumes:
        utils.echo('Found 0 volume')
        return
    utils.echo(f'Found {len(found_volumes)} volume(s):')
    for volume in found_volumes:
        utils.echo(f'{volume.id} {volume.name}')

    utils.echo()

    sure = utils.wait_user_input('Are you sure to cleanup this volumes (y/n):',
                                 {'y', 'yes', 'n', 'no'},
                                 'Please input (y/n):')

    if sure in {'n', 'no'}:
        return

    mgr.delete_volumes(found_volumes, workers=args.worker)


@parser.add_command(
    cli.Arg('pool', help='Rbd pool'),
    IntArg('-w', '--workers', default=1, help='Workers. Defaults to 1'))
def cleanup_rbd(args):
    """Cleanup RBD Image
    """
    mgr = manager.OpenstackManager()
    volumes = [
        'volume-{}'.format(vol.id) for vol in mgr.client.list_volumes()]
    lines = mgr.rbd_ls(args.pool)

    delete_images = [
        line for line in lines \
            if line and line.startswith('volume') and line not in volumes]
    LOG.info('Found %s image(s)', len(delete_images))
    if not delete_images:
        return
    utils.echo(delete_images, list_join='\n')
    utils.echo()

    sure = utils.wait_user_input('Are you sure to cleanup all vms (y/n):',
                                 {'y', 'yes', 'n', 'no'},
                                 'Please input (y/n):')

    if sure in {'n', 'no'}:
        return

    LOG.info('Try to delete %s image(s) with rbd', len(delete_images))
    def delete_image(image):
        return mgr.rbd_rm(args.pool, image)

    bar = pbr.factory(len(delete_images))
    with futures.ThreadPoolExecutor(max_workers=args.workers or 1) as executor:
        LOG.info('Deleting, please be patient ...')
        for _ in executor.map(delete_image, delete_images):
            bar.update(1)
        bar.close()


def main():
    parser.call()


if __name__ == '__main__':
    main()
