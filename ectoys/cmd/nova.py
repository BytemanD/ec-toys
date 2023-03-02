import logging
import functools
import typer

from easy2use.globals import log
from easy2use.globals import cli
from ectoys.modules.openstack import manager

from ectoys import utils

LOG = logging.getLogger(__name__)

CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])

app = typer.Typer(context_settings=CONTEXT_SETTINGS, help='EC Nova Utils')


@app.command(help='Cleanup vm')
@utils.init_log_from_command
def cleanup_vm(
    name: str=typer.Option(None, '-n', '--name', help='VM name'),
    host: str=typer.Option(None, '--host', help='VM host'),
    status: str=typer.Option(None, '-s', '--status', help='VM status'),
    workers: int=typer.Option(1, '-w',  '--workers',
                              help='Num of delete workers'),
    force: bool=typer.Option(False, '-f', '--force', help='Force delete'),
    debug: bool=typer.Option(False, '-d', '--debug', help='Show debug messag'),
):
    if all([not name, not host, not status]):
        no = {'n', 'no'}
        invalid_input = no.union({'y', 'yes'})
        sure = input('Are you sure to cleanup all vms (y/n):')
        while sure not in invalid_input:
            sure = input('Please input (y/n):')
        if sure in no:
            return
    mgr = manager.OpenstackManager()
    mgr.delete_vms(name=name, host=host, status=status, workers=workers,
                   force=force)


@app.command(context_settings=CONTEXT_SETTINGS, help='Attach inerface')
@utils.init_log_from_command
def attach_interface(
    server_id: str,
    net_id: str,
    num: int=typer.Option(1, '-n', '--num', help='VM status'),
    debug: bool=typer.Option(False, '-d', '--debug', help='Show debug messag'),
):
    mgr = manager.OpenstackManager()
    mgr.attach_interfaces(server_id, net_id, num=num)


@app.command(context_settings=CONTEXT_SETTINGS, help='Attach inerface')
@utils.init_log_from_command
def detach_interface(
    server_id: str,
    start: int=typer.Option(1, '-s', '--start',
                            help='Start index of vm interfaces'),
    end: int=typer.Option(None, '-e', '--end',
                          help='Start index of vm interfaces'),
):
    mgr = manager.OpenstackManager()
    mgr.detach_interfaces(server_id, start=start-1, end=end)


def main():
    app()


if __name__ == '__main__':
    main()
