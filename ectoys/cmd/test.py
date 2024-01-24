import logging
import sys
import pathlib
import click

from easy2use.globals import log

from ectoys.common import conf
from ectoys.common import exceptions
from ectoys.common import utils
from ectoys.common import log as context_log
from ectoys.common.test import scenario

CONF = conf.CONF
LOG = context_log.getLogger()

@click.group(context_settings={'help_option_names': ['-h', '--help']})
def main():
    pass


@main.command()
@click.option('-c', '--conf', 'conf_file')
@click.option('-d', '--debug', default=False, is_flag=True)
def vm_scenario_test(debug, conf_file):
    """Test VM
    """
    global LOG
    context_log.basic_config(debug=debug)
    log.basic_config(level=debug and logging.DEBUG or logging.INFO)

    LOG = context_log.getLogger()

    try:
        conf.load_configs(conf_file=conf_file)
        utils.load_env(CONF.openstack.env)
        
    except exceptions.ConfileNotExists as e:
        LOG.error('load config failed, {}', e)
        sys.exit(1)
    except exceptions.InvalidConfig as e:
        LOG.error('load env file failed, {}', e)
        sys.exit(1)

    LOG.info('start to test vm')

    if CONF.scenario_test.mode == 'process':
        scenario.process_test_vm()
    elif CONF.scenario_test.mode == 'coroutine':
        try:
            scenario.coroutine_test_vm()
        except Exception as e:
            LOG.error("test failed, {}", e)
    else:
        raise ValueError('Invalid config worker_mode')



if __name__ == '__main__':
    main()
