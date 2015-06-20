from __future__ import print_function

from rainbow_logging_handler import RainbowLoggingHandler
from delfick_error import DelfickError, UserQuit
import argparse
import logging
import sys
import os

class Ignore(object):
    pass

class BadOption(DelfickError):
    desc = "Bad option"

########################
###   APP
########################

class App(object):

    ########################
    ###   SETTABLE PROPERTIES
    ########################

    VERSION = Ignore
    """The version of your application, best way is to define this somewhere and import it into your mainline and setup.py from that location"""

    CliParserKls = property(lambda s: CliParser)
    """The class to use for our CliParser"""

    logging_handler_file = property(lambda s: sys.stderr)
    """The file to log output to (default is stderr)"""

    boto_useragent_name = Ignore
    """The name to append to your boto useragent if that's a thing you want to happen"""

    cli_description = "My amazing app"
    """The description to give at the top of --help output"""

    cli_positional_replacements = None
    """
    A list mapping positional arguments to --arguments

    For example

    cli_positional_replacements = ['--environment', '--stack']
    Will mean the first positional argument becomes the value for --environment and the second positional becomes the value for '--stack'
    Note for this to work, you must do something like

    def setup_other_args(self, parser, defaults):
        parser.add_argument('--environment'
            , help = "the environment!"
            , **defaults['--environment']
            )

    Items in positional_replacements may also be a tuple of (replacement, default)

    For example

    cli_positional_replacements = [('--task', 'list_tasks')]
    will mean the first positional argument becomes the value for --task
    But if it's not specified, then defaults['--task'] = {"default": "list_tasks"}
    """

    cli_environment_defaults = None
    """
    A map of environment variables to --argument that you want to map

    For example

    cli_environment_defaults = {"APP_CONFIG": "--config"}

    Items may also be a tuple of (replacement, default)

    For example, {"APP_CONFIG": ("--config", "./config.yml")}
    Which means defaults["--config"] = {'default': "./config.yml"} if APP_CONFIG isn't in the environment.
    """

    cli_categories = None
    """
    self.execute is passed a dictionary cli_args which is from looking at the args object returned by argparse

    This option will break up arguments into hierarchies based on the name of the argument.

    For example

    cli_categories = ['app']

    and we have arguments for [silent, verbose, debug, app_config, app_option1, app_option2]

    Then cli_args will be {"app": {"config": value, "option1": value, "option2": value}, "silent": value, "verbose": value, "debug": value}
    """

    ########################
    ###   USAGE
    ########################

    @classmethod
    def main(kls):
        app = kls()
        app.mainline()

    def execute(self, args, cli_args, logging_handler):
        """Hook for executing the application itself"""
        raise NotImplementedError()

    def setup_other_logging(self, args, verbose=False, silent=False, debug=False):
        """
        Hook for setting up any other logging configuration

        For example
        logging.getLogger("boto").setLevel([logging.CRITICAL, logging.ERROR][verbose or debug])
        logging.getLogger("requests").setLevel([logging.CRITICAL, logging.ERROR][verbose or debug])
        logging.getLogger("paramiko.transport").setLevel([logging.CRITICAL, logging.ERROR][verbose or debug])
        """

    def specify_other_args(self, parser, defaults):
        """
        Hook for adding more arguments to the argparse Parser

        For example

        parser.add_argument("--special"
            , help = "taste the rainbow"
            , action = "store_true"
            )
        """

    ########################
    ###   INTERNALS
    ########################

    def set_boto_useragent(self):
        """Make boto report this application as the user agent"""
        if self.boto_useragent_name is not Ignore and self.VERSION is not Ignore:
            __import__("boto")
            useragent = sys.modules["boto.connection"].UserAgent
            if self.boto_useragent_name not in useragent:
                sys.modules["boto.connection"].UserAgent = "{0} {1}/{2}".format(useragent, self.boto_useragent_name, self.VERSION)

    def mainline(self, argv=None):
        """
        The mainline for the application

        * Initialize parser and parse argv
        * Initialize the logging
        * run self.execute()
        * Catch and display DelfickError
        * Display traceback if we catch an error and args.debug
        """
        cli_parser = None
        try:
            cli_parser = self.make_cli_parser()
            try:
                args, cli_args = cli_parser.interpret_args(argv, self.cli_categories)
                handler = self.setup_logging(args, verbose=args.verbose, silent=args.silent, debug=args.debug)
                self.set_boto_useragent()
                self.execute(args, cli_args, handler)
            except KeyboardInterrupt:
                if cli_parser and cli_parser.parse_args(argv)[0].debug:
                    raise
                raise UserQuit()
        except DelfickError as error:
            print("")
            print("!" * 80)
            print("Something went wrong! -- {0}".format(error.__class__.__name__))
            print("\t{0}".format(error))
            if cli_parser and cli_parser.parse_args(argv)[0].debug:
                raise
            sys.exit(1)

    def setup_logging(self, args, verbose=False, silent=False, debug=False):
        """Setup the RainbowLoggingHandler for the logs and call setup_other_logging"""
        log = logging.getLogger("")
        handler = RainbowLoggingHandler(self.logging_handler_file)
        handler._column_color['%(asctime)s'] = ('cyan', None, False)
        handler._column_color['%(levelname)-7s'] = ('green', None, False)
        handler._column_color['%(message)s'][logging.INFO] = ('blue', None, False)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)-15s %(message)s"))
        log.addHandler(handler)
        log.setLevel([logging.INFO, logging.DEBUG][verbose or debug])
        if silent:
            log.setLevel(logging.ERROR)

        self.setup_other_logging(args, verbose, silent, debug)
        return handler

    def make_cli_parser(self):
        """Return a CliParser instance"""
        properties = {"specify_other_args": self.specify_other_args}
        return type("CliParser", (self.CliParserKls, ), properties)(self.cli_description, self.cli_positional_replacements, self.cli_environment_defaults)

########################
###   CliParser
########################

class CliParser(object):
    """Knows what argv looks like"""
    def __init__(self, description, positional_replacements=None, environment_defaults=None):
        self.description = description
        self.positional_replacements = positional_replacements
        if self.positional_replacements is None:
            self.positional_replacements = []

        self.environment_defaults = environment_defaults
        if self.environment_defaults is None:
            self.environment_defaults = {}

    def parse_args(self, argv=None):
        """
        Build up an ArgumentParser and parse our argv!

        Also complain if any --argument is both specified explicitly and as a positional
        """
        args, other_args, defaults = self.split_args(argv)
        parser = self.make_parser(defaults)
        args = parser.parse_args(args)

        for index, replacement in enumerate(self.positional_replacements):
            if type(replacement) is tuple:
                replacement, _ = replacement
            if replacement in defaults and replacement in args:
                raise BadOption("Please don't specify a task as a positional argument and as a --argument", argument=replacement, position=index+1)

        return args, other_args

    def interpret_args(self, argv, categories=None):
        """
        Parse argv and return (args, extra, cli_args)

        Where args is the object return by argparse
        extra is all the arguments after a --
        and cli_args is a dictionary representation of the args object
        """
        if categories is None:
            categories = []
        args, extra = self.parse_args(argv)

        cli_args = {}
        for category in categories:
            cli_args[category] = {}
        for key, val in sorted(vars(args).items()):
            found = False
            for category in categories:
                if key.startswith("{0}_".format(category)):
                    cli_args[category][key[(len(category)+1)]] = val
                    found = True
                    break

            if not found:
                cli_args[key] = val

        return args, extra, cli_args


    def split_args(self, argv):
        """
        Split up argv into args, other_args and defaults

        Defaults are populated from mapping environment_defaults to --arguments
        and mapping positional_replacements to --arguments

        So if positional_replacements is [--stack] and argv is ["blah", "--stuff", 1]
        defaults will equal {"--stack": {"default": "blah"}}

        If environment_defaults is {"CONFIG_LOCATION": "--config"}
        and os.environ["CONFIG_LOCATION"] = "/a/path/to/somewhere.yml"
        then defaults will equal {"--config": {"default": "/a/path/to/somewhere.yml"}}

        Positional arguments will override environment defaults.

        Other args is anything after a "--" and args is everything before a "--"
        """
        if argv is None:
            argv = sys.argv[1:]

        argv = list(argv)
        args = []
        extras = None
        defaults = {}

        class Ignore(object): pass

        for env_name, replacement in self.environment_defaults.items():
            default = Ignore
            if type(replacement) is tuple:
                replacement, default = replacement

            if env_name in os.environ:
                defaults[replacement] = {"default": os.environ[env_name]}
            else:
                if default is Ignore:
                    defaults[replacement] = {}
                else:
                    defaults[replacement] = {"default": default}

        for replacement in self.positional_replacements:
            if type(replacement) is tuple:
                replacement, _ = replacement
            if argv and not argv[0].startswith("-"):
                defaults[replacement] = {"default": argv[0]}
                argv.pop()
            else:
                break

        for replacement in self.positional_replacements:
            default = Ignore
            if type(replacement) is tuple:
                replacement, default = replacement
            if replacement not in defaults:
                if default is Ignore:
                    defaults[replacement] = {}
                else:
                    defaults[replacement] = {"default": default}

        while argv:
            nxt = argv.pop(0)
            if extras is not None:
                extras.append(nxt)
            elif nxt == "--":
                extras = []
            else:
                args.append(nxt)

        other_args = ""
        if extras:
            other_args = " ".join(extras)

        return args, other_args, defaults

    def make_parser(self, defaults):
        """Create an argparse ArgumentParser, setup --verbose, --silent, --debug and call specify_other_args"""
        parser = argparse.ArgumentParser(description=self.description)

        logging = parser.add_mutually_exclusive_group()
        logging.add_argument("--verbose"
            , help = "Enable debug logging"
            , action = "store_true"
            )

        logging.add_argument("--silent"
            , help = "Only log errors"
            , action = "store_true"
            )

        logging.add_argument("--debug"
            , help = "Debug logs"
            , action = "store_true"
            )

        self.specify_other_args(parser, defaults)
        return parser
