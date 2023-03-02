from easy2use.globals import cli


class IntArg(cli.Arg):

    def __init__(self, *args, **kwargs):
        if 'type' in kwargs and kwargs.get('type') != int:
            raise ValueError('type must be "int"')
        kwargs['type'] = int
        super().__init__(*args, **kwargs)


class BoolArg(cli.Arg):

    def __init__(self, *args, **kwargs):
        if 'action' in kwargs and kwargs.get('action') != 'store_true':
            raise ValueError('action must be "store_true"')
        kwargs['action'] = 'store_true'
        super().__init__(*args, **kwargs)


log_arg_group = cli.ArgGroup(
    'Log options',
    [BoolArg('-d', '--debug', help='Show debug messag')]
)
