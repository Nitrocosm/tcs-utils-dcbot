"""Centralised logging setup for the bot.

Call `setup()` once at startup (before `bot.run()`). Every module should get
its own logger via `logging.getLogger(__name__)` and log through that.
"""
import logging
import sys

_FORMAT = '%(asctime)s %(levelname)-8s %(name)s: %(message)s'
_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


def setup(level: int = logging.INFO) -> None:
    """Configure the root logger with a single stdout handler.

    Safe to call more than once — existing handlers are cleared first so
    handlers never stack up. `bot.run()` should be passed `log_handler=None`
    so discord.py does not add a second handler of its own.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
