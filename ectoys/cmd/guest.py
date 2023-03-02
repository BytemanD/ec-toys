import libvirt
import logging
import pathlib

import typer
import typing

from easy2use.globals import cli
from easy2use.globals import log

from ectoys.cmd import IntArg
from ectoys.cmd import BoolArg
from ectoys.cmd import log_arg_group
from ectoys.modules import guest


LOG = logging.getLogger(__name__)


parser = cli.SubCliParser('EC Guest Utils')


@parser.add_command(
    cli.Arg('domain', help='Domain name or uuid'),
    cli.Arg('cmd', help='Command'),
    cli.Arg('--host', default='localhost', help='Guest host'),
    log_arg_group)
def cmd(args):
    """Execute command on guest by QGA
    """
    instance = guest.Guest(args.domain, host=args.host)
    try:
        result = instance.guest_exec(cmd)
        typer.echo(result)
    except guest.DomainNotFound as e:
        typer.echo(e)
    except libvirt.libvirtError as e:
        typer.echo(e.get_error_message())

@parser.add_command(
    cli.Arg('domain', help='Domain name or id'),
    cli.Arg('xml', help='The path of xml file'),
    cli.Arg('--host', default='localhost', help='Guest host'),
    BoolArg('-p', '--persistent', help='Update with config flag'),
    BoolArg('-l', '--live', help='Update with live flag'),
    log_arg_group)
def update_device(args):
    """Update guest device
    """
    xml_path = pathlib.Path(args.xml)
    if not xml_path.exists():
        typer.echo(FileNotFoundError(f'ERROR: File {args.xml} not exists'))
        return 1
    if not xml_path.is_file():
        typer.echo(ValueError(f'ERROR: Path {args.xml} is not file'))
        return 1

    instance = guest.Guest(args.domain, host=args.host)
    instance.update_device(xml_path,
                           persistent=args.persistent, live=args.live)


def main():
    parser.call()


if __name__ == '__main__':
    main()
