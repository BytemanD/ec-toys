import logging

from easy2use.globals import cli
from easy2use.downloader.urllib import driver

from ectoys.cmd import IntArg
from ectoys.cmd import log_arg_group

LOG = logging.getLogger(__name__)

parser = cli.SubCliParser('EC Guest Utils')


@parser.add_command(
    cli.Arg('url', help='The url of yum repo.'),
    IntArg('-w', '--workers', default=1, help='Download worker. Defaults to 1'),
    log_arg_group)
def download_rpm(args):
    """Download rpm packags from URL
    """
    links = driver.find_links(args.url, link_regex=r'.+\.rpm')
    LOG.debug('found %s link(s)', len(links))

    downloader = driver.Urllib3Driver(progress=True, workers=args.workers)
    downloader.download_urls([f'{args.url}/{rpm}' for rpm in links])


def main():
    parser.call()


if __name__ == '__main__':
    main()
