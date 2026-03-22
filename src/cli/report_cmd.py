"""Report subcommand: stats → charts → Slack."""

import sys
from datetime import datetime, timedelta
from typing import Optional

from src.bot.reporter import generate_daily_report, generate_weekly_report
from src.es_client.client import ElasticsearchClient
from src.kibana.capture import KibanaCapture
from src.slack.client import SlackClient
from src.utils.config import AppConfig
from src.utils.date_utils import get_current_time
from src.utils.logger import get_logger

logger = get_logger(__name__)


def run_report_command(args, cfg: AppConfig) -> None:
    """Wire argparse namespace to ES / Slack / Kibana and report generators."""
    report_anchor: Optional[datetime] = None
    if args.date:
        try:
            report_anchor = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            logger.error(f"Invalid date format: {args.date}. Use YYYY-MM-DD format.")
            sys.exit(1)
    else:
        report_anchor = get_current_time() - timedelta(days=1)

    try:
        es_client = ElasticsearchClient(cfg.elasticsearch)
    except Exception as e:
        logger.error(f"Failed to connect to Elasticsearch: {e}")
        sys.exit(1)

    channel_id = args.channel or cfg.slack.channel_id
    slack_client: Optional[SlackClient] = None
    if not args.dry_run:
        slack_client = SlackClient(token=cfg.slack.api_token, channel_id=channel_id, dummy=False)

    kibana_capture: Optional[KibanaCapture] = None
    if args.type == "weekly" and not args.dry_run:
        kibana_capture = KibanaCapture.from_config(cfg)

    if args.type == "daily":
        generate_daily_report(
            es_client,
            cfg,
            slack_client,
            channel_id=channel_id,
            channel_name=args.channel,
            target_date=report_anchor,
            dry_run=args.dry_run,
        )
    elif args.type == "weekly":
        generate_weekly_report(
            es_client,
            cfg,
            slack_client,
            kibana_capture,
            channel_id=channel_id,
            channel_name=args.channel,
            end_date=report_anchor,
            dry_run=args.dry_run,
        )
    else:
        logger.error(f"Unknown report type: {args.type}")
        sys.exit(1)
