import logging

import typer

from easy2use.globals import log
from ectoys.modules.openstack import manager
from ectoys.modules.openstack import exceptions

LOG = logging.getLogger(__name__)

CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])

app = typer.Typer(context_settings=CONTEXT_SETTINGS,
                  help='EC Nova Utils')


@app.command(context_settings=CONTEXT_SETTINGS, help='Cleanup vm')
def create_volume(
    size: int,
    num: int=typer.Option(1, '-n', '--num', help='Num to create'),
    name: str=typer.Option(None, '--name',
                           help='Volume name. Defaults to a random string'),

    image: str=typer.Option(None, '-i', '--image', help='Image id'),
    snapshot: str=typer.Option(None, '-s', '--snapshot', help='Snapshot id'),
    vol_type: str=typer.Option(None, '-t', '--type', help='Volume type'),
    workers: int=typer.Option(1, '-w',  '--workers',
                              help='Defaults to use the same value as num'),
    debug: bool=typer.Option(False, '-d', '--debug', help='Show debug messag'),
):
    log.basic_config(logging.DEBUG if debug else logging.INFO)

    if image and snapshot:
        raise exceptions.InvalidArgs(
            reason='--image and --snapshot can not specify both')

    mgr = manager.OpenstackManager()
    volumes = mgr.create_volumes(size, name, num=num, image=image,
                                 snapshot=snapshot, volume_type=vol_type,
                                 workers=workers)
    typer.echo('new volumes:')
    typer.echo("\n".join(volumes))


def main():
    app()


if __name__ == '__main__':
    main()
