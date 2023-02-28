import logging

import typer

from easy2use.globals import log
from ectoys.modules.openstack import manager

LOG = logging.getLogger(__name__)

CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])

app = typer.Typer(context_settings=CONTEXT_SETTINGS,
                  help='EC Nova Utils')


@app.command(context_settings=CONTEXT_SETTINGS, help='Cleanup vm')
def cleanup_vm(
    name: str=typer.Option(None, '-n', '--name', help='VM name'),
    host: str=typer.Option(None, '--host', help='VM host'),
    status: str=typer.Option(None, '-s', '--status', help='VM status'),
    workers: int=typer.Option(1, '-w',  '--workers',
                              help='Num of delete workers'),
    debug: bool=typer.Option(False, '-d', '--debug', help='Show debug messag'),
):
    log.basic_config(logging.DEBUG if debug else logging.INFO)

    if all([not name, not host, not status]):
        no = {'n', 'no'}
        invalid_input = no.union({'y', 'yes'})
        sure = input('Are you sure to cleanup all vms (y/n):')
        while sure not in invalid_input:
            sure = input('Please input (y/n):')

        if sure in no:
            return

    mgr = manager.OpenstackManager()
    mgr.delete_vms(name=name, host=host, status=status, workers=workers)


def main():
    app()


if __name__ == '__main__':
    main()
