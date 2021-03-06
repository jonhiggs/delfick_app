from __future__ import print_function

from rainbow_logging_handler import RainbowLoggingHandler
from delfick_error import DelfickError, UserQuit
import argparse
import logging
import sys
import os

log = logging.getLogger("delfick_app")

class Ignore(object):
    pass

class BadOption(DelfickError):
    desc = "Bad option"

########################
###   APP
########################

class App(object):
    """
    .. automethod:: main

    ``Attributes``

        .. autoattribute:: VERSION

            The version of your application, best way is to define this somewhere and import it into your mainline and setup.py from that location

        .. autoattribute:: CliParserKls

            The class to use for our CliParser

        .. autoattribute:: logging_handler_file

            The file to log output to (default is stderr)

        .. autoattribute:: boto_useragent_name

            The name to append to your boto useragent if that's a thing you want to happen

        .. autoattribute:: cli_categories

            self.execute is passed a dictionary cli_args which is from looking at the args object returned by argparse

            This option will break up arguments into hierarchies based on the name of the argument.

            For example:

            ``cli_categories = ['app']``

            and we have arguments for ``[silent, verbose, debug, app_config, app_option1, app_option2]``

            Then cli_args will be ``{"app": {"config": value, "option1": value, "option2": value}, "silent": value, "verbose": value, "debug": value}``

        .. autoattribute:: cli_description

            The description to give at the top of --help output

        .. autoattribute:: cli_environment_defaults

            A map of environment variables to --argument that you want to map

            For example:

            ``cli_environment_defaults = {"APP_CONFIG": "--config"}``

            Items may also be a tuple of ``(replacement, default)``

            For example, ``{"APP_CONFIG": ("--config", "./config.yml")}``

            Which means ``defaults["--config"] == {'default': "./config.yml"}`` if APP_CONFIG isn't in the environment.

        .. autoattribute:: cli_positional_replacements

            A list mapping positional arguments to --arguments

            For example:

            ``cli_positional_replacements = ['--environment', '--stack']``
                Will mean the first positional argument becomes the value for --environment and the second positional becomes the value for '--stack'

                Note for this to work, you must do something like:

                .. code-block:: python

                    def setup_other_args(self, parser, defaults):
                        parser.add_argument('--environment'
                            , help = "the environment!"
                            , **defaults['--environment']
                            )

            Items in positional_replacements may also be a tuple of ``(replacement, default)``

            For example:

            ``cli_positional_replacements = [('--task', 'list_tasks')]``
                will mean the first positional argument becomes the value for --task

                But if it's not specified, then ``defaults['--task'] == {"default": "list_tasks"}``

    ``Hooks``

        .. automethod:: execute

        .. automethod:: setup_other_logging

        .. automethod:: specify_other_args
    """

    ########################
    ###   SETTABLE PROPERTIES
    ########################

    VERSION = Ignore
    boto_useragent_name = Ignore

    CliParserKls = property(lambda s: CliParser)
    logging_handler_file = property(lambda s: sys.stderr)

    cli_categories = None
    cli_description = "My amazing app"
    cli_environment_defaults = None
    cli_positional_replacements = None

    ########################
    ###   USAGE
    ########################

    @classmethod
    def main(kls):
        """
        Instantiates this class and calls the mainline

        Usage is intended to be:

        .. code-block:: python

            from delfick_app import App

            class MyApp(App):
                [..]

            main = MyApp.main
        """
        app = kls()
        app.mainline()

    def execute(self, args, extra_args, cli_args, logging_handler):
        """Hook for executing the application itself"""
        raise NotImplementedError()

    def setup_other_logging(self, args, verbose=False, silent=False, debug=False):
        """
        Hook for setting up any other logging configuration

        For example:

        .. code-block:: python

            def setup_other_logging(self, args, verbose, silent, debug):
                logging.getLogger("boto").setLevel([logging.CRITICAL, logging.ERROR][verbose or debug])
                logging.getLogger("requests").setLevel([logging.CRITICAL, logging.ERROR][verbose or debug])
                logging.getLogger("paramiko.transport").setLevel([logging.CRITICAL, logging.ERROR][verbose or debug])
        """

    def specify_other_args(self, parser, defaults):
        """
        Hook for adding more arguments to the argparse Parser

        For example:

        .. code-block:: python

            def specify_other_args(self, parser, defaults):
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

    def mainline(self, argv=None, print_errors_to=sys.stdout):
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
                args, extra_args, cli_args = cli_parser.interpret_args(argv, self.cli_categories)
                handler = self.setup_logging(args, verbose=args.verbose, silent=args.silent, debug=args.debug)
                self.set_boto_useragent()
                self.execute(args, extra_args, cli_args, handler)
            except KeyboardInterrupt:
                if cli_parser and cli_parser.parse_args(argv)[0].debug:
                    raise
                raise UserQuit()
        except DelfickError as error:
            print("", file=print_errors_to)
            print("!" * 80, file=print_errors_to)
            print("Something went wrong! -- {0}".format(error.__class__.__name__), file=print_errors_to)
            print("\t{0}".format(error), file=print_errors_to)
            if cli_parser and cli_parser.parse_args(argv)[0].debug:
                raise
            sys.exit(1)

    def setup_logging(self, args, verbose=False, silent=False, debug=False, logging_name=""):
        """Setup the RainbowLoggingHandler for the logs and call setup_other_logging"""
        log = logging.getLogger(logging_name)
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

    def setup_logging_theme(self, handler, colors="light"):
        """
        Setup a logging theme

        Currently there is only ``light`` and ``dark`` which consists of a difference
        in color for INFO level messages.
        """
        if colors not in ("light", "dark"):
            log.warning("Told to set colors to a theme we don't have\tgot=%s\thave=[light, dark]", colors)
            return

        # Haven't put much effort into actually working out more than just the message colour
        if colors == "light":
            handler._column_color['%(message)s'][logging.INFO] = ('cyan', None, False)
        else:
            handler._column_color['%(message)s'][logging.INFO] = ('blue', None, False)

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

    def specify_other_args(self, parser, defaults):
        """Hook to specify more arguments"""

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
                    cli_args[category][key[(len(category)+1):]] = val
                    found = True
                    break

            if not found:
                cli_args[key] = val

        return args, extra, cli_args

    def parse_args(self, argv=None):
        """
        Build up an ArgumentParser and parse our argv!

        Also complain if any --argument is both specified explicitly and as a positional
        """
        args, other_args, defaults = self.split_args(argv)
        parser = self.make_parser(defaults)
        parsed = parser.parse_args(args)
        self.check_args(args, defaults, self.positional_replacements)
        return parsed, other_args

    def check_args(self, args, defaults, positional_replacements):
        """Check that we haven't specified an arg as positional and a --flag"""
        for index, replacement in enumerate(positional_replacements):
            if type(replacement) is tuple:
                replacement, _ = replacement
            if "default" in defaults.get(replacement, {}) and replacement in args:
                raise BadOption("Please don't specify an option as a positional argument and as a --flag", argument=replacement, position=index+1)

    def split_args(self, argv):
        """
        Split up argv into args, other_args and defaults

        Other args is anything after a "--" and args is everything before a "--"
        """
        if argv is None:
            argv = sys.argv[1:]

        args = []
        argv = list(argv)
        extras = None

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

        defaults = self.make_defaults(args, self.positional_replacements, self.environment_defaults)
        return args, other_args, defaults

    def make_defaults(self, argv, positional_replacements, environment_defaults):
        """
        Make and return a dictionary of {--flag: {"default": value}}

        This method will also remove the positional arguments from argv
        that map to positional_replacements.

        Defaults are populated from mapping environment_defaults to --arguments
        and mapping positional_replacements to --arguments

        So if positional_replacements is [--stack] and argv is ["blah", "--stuff", 1]
        defaults will equal {"--stack": {"default": "blah"}}

        If environment_defaults is {"CONFIG_LOCATION": "--config"}
        and os.environ["CONFIG_LOCATION"] = "/a/path/to/somewhere.yml"
        then defaults will equal {"--config": {"default": "/a/path/to/somewhere.yml"}}

        Positional arguments will override environment defaults.
        """
        defaults = {}

        class Ignore(object): pass

        for env_name, replacement in environment_defaults.items():
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

        for replacement in positional_replacements:
            if type(replacement) is tuple:
                replacement, _ = replacement
            if argv and not argv[0].startswith("-"):
                defaults[replacement] = {"default": argv[0]}
                argv.pop(0)
            else:
                break

        for replacement in positional_replacements:
            default = Ignore
            if type(replacement) is tuple:
                replacement, default = replacement
            if replacement not in defaults:
                if default is Ignore:
                    defaults[replacement] = {}
                else:
                    defaults[replacement] = {"default": default}

        return defaults

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

