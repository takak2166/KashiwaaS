"""
CLI entry: fetch / report subcommands. Run via ``python -m src.cli``.

Implementation: ``args`` (parser), ``fetch_cmd``, ``report_cmd``.
"""

import sys

from src.bot.alerter import init_alerter
from src.cli.args import parse_args
from src.cli.fetch_cmd import run_fetch_command
from src.cli.report_cmd import run_report_command
from src.utils.config import ConfigError, apply_dotenv, load_config, validate_cli_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


def main() -> None:
    apply_dotenv()
    try:
        cfg = load_config()
        args = parse_args()
        if args.command == "fetch" and getattr(args, "dummy", False):
            validate_cli_config(cfg, require_slack_credentials=False)
        elif args.command in ("fetch", "report"):
            validate_cli_config(cfg)
    except ConfigError as e:
        logger.error("%s", e)
        sys.exit(1)

    init_alerter(cfg)

    if args.command == "fetch":
        run_fetch_command(args, cfg)
    elif args.command == "report":
        run_report_command(args, cfg)
    else:
        logger.error("No command specified. Use --help for usage information.")
        sys.exit(1)


if __name__ == "__main__":
    main()
