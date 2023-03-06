import functools
import logging
import json

from easy2use.globals import log


def init_log_from_command(func):

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        log.basic_config(
            kwargs.get('debug') and logging.DEBUG or logging.INFO
        )
        func(*args, **kwargs)

    return wrapper


def wait_user_input(prompt, valid_values, invalid_help):
    user_input = input(prompt)
    while user_input not in valid_values:
        user_input = input(invalid_help)

    return user_input


# TODO: move this to easy2use
def echo(message=None, list_join: str=None):
    if isinstance(message, bytes):
        print(message.decode())
        return
    if isinstance(message, list) and list_join:
        print(list_join.join(message))
        return
    if isinstance(message, dict):
        print(json.dumps(message, indent=True))

    print(message or '')
