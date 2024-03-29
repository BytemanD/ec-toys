import functools
import json
import os
import time
import pathlib

from easy2use import date
from ectoys.common import exceptions


def wait_user_input(prompt, valid_values, invalid_help):
    user_input = input(prompt)
    while user_input not in valid_values:
        user_input = input(invalid_help)

    return user_input


def load_env(env_file):
    if not env_file or not pathlib.Path(env_file).is_file():
        raise exceptions.InvalidConfig(
            reason='env file is not set or not exists')

    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.strip().startswith('#'):
                continue
            env = line.split()[-1]
            if not env:
                continue
            k, v = env.split('=')
            os.environ[k] = v


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


def do_times(options=None):
    def wrapper(func):
        @functools.wraps(func)
        def wrapper_func(*args, **kwargs):
            run_times, run_interval = (options.times, options.interval) \
                if options else (1, 1)
            LOG.info('do %s %s time(s)', func.__name__, run_times)
            for i in range(run_times):
                LOG.debug('do %s %s', func.__name__, i + 1)
                result = func(*args, **kwargs)
                time.sleep(run_interval)
            return result

        return wrapper_func

    return wrapper


# TODO: move this to easy2use
def run_processes(func, maps=None, max_workers=1, nums=None):
    from concurrent import futures

    with futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        if maps:
            tasks = executor.map(func, maps)
        elif nums:
            tasks = [executor.submit(func) for _ in range(nums)]
        for future in futures.as_completed(tasks):
            yield future.result()

def generate_name(resource):
    return 'ecToys-{}-{}'.format(resource,
                                 date.now_str(date_fmt='%m%d-%H:%M:%S'))
