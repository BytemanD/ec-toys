import libvirt
import pathlib

from easy2use.globals import cli
from ectoys.cmd import BoolArg
from ectoys.cmd import log_arg_group
from ectoys.modules import guest
from ectoys.common import utils


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
        result = instance.guest_exec(args.cmd)
        utils.echo(result)
    except guest.DomainNotFound as e:
        print(e)
    except libvirt.libvirtError as e:
        print(e)

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
        utils.echo(FileNotFoundError(f'ERROR: File {args.xml} not exists'))
        return 1
    if not xml_path.is_file():
        utils.echo(ValueError(f'ERROR: Path {args.xml} is not file'))
        return 1

    instance = guest.Guest(args.domain, host=args.host)
    instance.update_device(xml_path,
                           persistent=args.persistent, live=args.live)


def main():
    parser.call()


if __name__ == '__main__':
    main()
