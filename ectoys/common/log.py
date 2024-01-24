import sys
from loguru import logger

DEFAULT_FOAMAT = '{time:YYYY-MM-DD HH:mm:ss} {process} <level>{level:7}</level> ' \
                 '<level>[vm: {extra[vm]}] {message}</level>'

LOG = logger.bind(vm='-')


def basic_config(debug=False):
    global LOG

    logger.configure(handlers=[{
        "sink": sys.stdout,
        'format': DEFAULT_FOAMAT,
        "colorize": True,
        "level": "DEBUG" if debug else "INFO",
    }])


def getLogger():
    return LOG
