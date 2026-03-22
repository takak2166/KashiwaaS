"""
CLI entry: fetch / report subcommands. Run via ``python -m src.cli``.

Implementation: ``args`` (parser), ``fetch_cmd``, ``report_cmd``.
"""

import sys

from src.cli.args import parse_args
from src.cli.fetch_cmd import run_fetch_command
from src.cli.report_cmd import run_report_command
from src.utils.config import config
from src.utils.logger import get_logger

logger = get_logger(__name__)


def main() -> None:
    if not config:
        logger.error("Configuration is not properly loaded. Please check your .env file.")
        sys.exit(1)

    args = parse_args()

    if args.command == "fetch":
        run_fetch_command(args)
    elif args.command == "report":
        run_report_command(args)
    else:
        logger.error("No command specified. Use --help for usage information.")
        sys.exit(1)


if __name__ == "__main__":
    main()
