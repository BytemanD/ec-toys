import libvirt
import logging
import pathlib

import typer
import typing

from easy2use.globals import log
from ectoys.modules import guest

LOG = logging.getLogger(__name__)

CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])

app = typer.Typer(context_settings=CONTEXT_SETTINGS,
                  help='EC Guest Utils')


@app.command(context_settings=CONTEXT_SETTINGS, help='Execute cmd in guest')
def cmd(
    domain: str, cmd: str,
    debug: bool=typer.Option(False, '-d', '--debug', help='Show debug messag'),
    host: str=typer.Option('localhost')
):
    log.basic_config(logging.DEBUG if debug else logging.INFO)

    instance = guest.Guest(host, domain)
    try:
        result = instance.guest_exec(cmd)
        typer.echo(result)
    except guest.DomainNotFound as e:
        typer.echo(e)
    except libvirt.libvirtError as e:
        typer.echo(e.get_error_message())


@app.command(context_settings=CONTEXT_SETTINGS, help='Update guest device')
def update_device(
    domain: str,
    xml: typing.Optional[pathlib.Path],
    host: str=typer.Option('localhost'),
    persistent: bool=typer.Option(False, '-p', '--persistent',
                                  help='Update with config flag'),
    live: bool=typer.Option(False, '-l', '--live',
                            help='Update with live flag'),
    debug: bool=typer.Option(False, '-d', '--debug', help='Show debug messag'),
):
    log.basic_config(logging.DEBUG if debug else logging.INFO)

    if not xml.exists():
        typer.echo(FileNotFoundError(f'ERROR: File {xml} not exists'))
        return 1

    instance = guest.Guest(host, domain)
    with open(xml) as f:
        device_xml = ''.join(f.readlines())
        instance.update_device(device_xml, persistent=persistent, live=live)


def main():
    app()


if __name__ == '__main__':
    main()
