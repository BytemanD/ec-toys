import functools
import logging

from easy2use.globals import log

from inspect import signature

def init_log_from_command(func):

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        log.basic_config(
            kwargs.get('debug') and logging.DEBUG or logging.INFO
        )
        func(*args, **kwargs)

    return wrapper
