"""
Kibana Dashboard Module
Provides functionality for managing Kibana dashboards
"""

import json
from typing import Any, Dict, Optional

import requests

from src.utils.config import config
from src.utils.logger import get_logger


logger = get_logger(__name__)


class KibanaDashboard:
    """
    Kibana Dashboard Manager

    Handles operations related to Kibana dashboards
    """

    def __init__(
        self,
        host: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """
        Initialize Kibana Dashboard Manager

        Args:
            host: Kibana host URL (default: http://kibana:5601)
            username: Kibana username (if authentication is enabled)
            password: Kibana password (if authentication is enabled)
        """
        self.host = host or config.kibana.host
        self.username = username or config.kibana.username
        self.password = password or config.kibana.password

        # Base URL for Kibana API
        self.api_base = f"{self.host}/api"

        # Authentication
        self.auth = None
        if self.username and self.password:
            self.auth = (self.username, self.password)

        logger.info(f"Initialized Kibana Dashboard Manager with host: {self.host}")

    def get_dashboard(self, dashboard_id: str) -> Dict[str, Any]:
        """
        Get dashboard by ID

        Args:
            dashboard_id: Dashboard ID

        Returns:
            Dict[str, Any]: Dashboard definition
        """
        url = f"{self.api_base}/dashboards/dashboard/{dashboard_id}"

        try:
            response = requests.get(url, auth=self.auth)
            response.raise_for_status()

            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get dashboard {dashboard_id}: {e}")
            return {}

    def create_dashboard(self, dashboard_def: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new dashboard

        Args:
            dashboard_def: Dashboard definition

        Returns:
            Dict[str, Any]: Created dashboard
        """
        url = f"{self.api_base}/dashboards/dashboard"

        try:
            response = requests.post(url, json=dashboard_def, auth=self.auth, headers={"kbn-xsrf": "true"})
            response.raise_for_status()

            logger.info(f"Created dashboard: {dashboard_def.get('title')}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create dashboard: {e}")
            return {}

    def update_dashboard(self, dashboard_id: str, dashboard_def: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing dashboard

        Args:
            dashboard_id: Dashboard ID
            dashboard_def: Dashboard definition

        Returns:
            Dict[str, Any]: Updated dashboard
        """
        url = f"{self.api_base}/dashboards/dashboard/{dashboard_id}"

        try:
            response = requests.put(url, json=dashboard_def, auth=self.auth, headers={"kbn-xsrf": "true"})
            response.raise_for_status()

            logger.info(f"Updated dashboard: {dashboard_def.get('title')}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to update dashboard: {e}")
            return {}

    def delete_dashboard(self, dashboard_id: str) -> bool:
        """
        Delete a dashboard

        Args:
            dashboard_id: Dashboard ID

        Returns:
            bool: True if successful, False otherwise
        """
        url = f"{self.api_base}/dashboards/dashboard/{dashboard_id}"

        try:
            response = requests.delete(url, auth=self.auth, headers={"kbn-xsrf": "true"})
            response.raise_for_status()

            logger.info(f"Deleted dashboard: {dashboard_id}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to delete dashboard {dashboard_id}: {e}")
            return False

    def get_dashboard_url(self, dashboard_id: str) -> str:
        """
        Get URL for a dashboard

        Args:
            dashboard_id: Dashboard ID

        Returns:
            str: Dashboard URL
        """
        return f"{self.host}/app/dashboards#/view/{dashboard_id}"

    def export_dashboard(self, dashboard_id: str, output_path: str) -> bool:
        """
        Export dashboard to file

        Args:
            dashboard_id: Dashboard ID
            output_path: Output file path

        Returns:
            bool: True if successful, False otherwise
        """
        dashboard = self.get_dashboard(dashboard_id)

        if not dashboard:
            logger.error(f"Dashboard {dashboard_id} not found")
            return False

        try:
            with open(output_path, "w") as f:
                json.dump(dashboard, f, indent=2)

            logger.info(f"Exported dashboard {dashboard_id} to {output_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to export dashboard {dashboard_id}: {e}")
            return False

    def import_dashboard(self, input_path: str) -> Dict[str, Any]:
        """
        Import dashboard from file

        Args:
            input_path: Input file path

        Returns:
            Dict[str, Any]: Created/updated dashboard
        """
        try:
            with open(input_path, "r") as f:
                dashboard_def = json.load(f)

            # Check if dashboard already exists
            dashboard_id = dashboard_def.get("id")
            if dashboard_id:
                existing = self.get_dashboard(dashboard_id)
                if existing:
                    # Update existing dashboard
                    result = self.update_dashboard(dashboard_id, dashboard_def)
                    logger.info(f"Updated dashboard from {input_path}")
                    return result

            # Create new dashboard
            result = self.create_dashboard(dashboard_def)
            logger.info(f"Created dashboard from {input_path}")
            return result
        except Exception as e:
            logger.error(f"Failed to import dashboard from {input_path}: {e}")
            return {}


# Default dashboard definitions
DAILY_DASHBOARD = {
    "title": "Slack Daily Activity",
    "description": "Daily activity metrics for Slack channels",
    "panels": [
        {
            "title": "Message Count by Hour",
            "type": "visualization",
            "visualization_type": "bar",
            "params": {
                "x_axis_field": "hour_of_day",
                "y_axis_field": "doc_count",
                "interval": "hour",
            },
        },
        {
            "title": "Top Users",
            "type": "visualization",
            "visualization_type": "table",
            "params": {"field": "username", "size": 10},
        },
        {
            "title": "Top Reactions",
            "type": "visualization",
            "visualization_type": "table",
            "params": {"field": "reactions.name", "size": 10},
        },
    ],
}

WEEKLY_DASHBOARD = {
    "title": "Slack Weekly Activity",
    "description": "Weekly activity metrics for Slack channels",
    "panels": [
        {
            "title": "Message Count by Day",
            "type": "visualization",
            "visualization_type": "line",
            "params": {
                "x_axis_field": "timestamp",
                "y_axis_field": "doc_count",
                "interval": "day",
            },
        },
        {
            "title": "Activity Heatmap",
            "type": "visualization",
            "visualization_type": "heatmap",
            "params": {
                "x_axis_field": "hour_of_day",
                "y_axis_field": "day_of_week",
                "value_field": "doc_count",
            },
        },
        {
            "title": "Top Users",
            "type": "visualization",
            "visualization_type": "table",
            "params": {"field": "username", "size": 10},
        },
        {
            "title": "Top Reactions",
            "type": "visualization",
            "visualization_type": "table",
            "params": {"field": "reactions.name", "size": 10},
        },
    ],
}


def setup_default_dashboards(kibana: KibanaDashboard) -> Dict[str, str]:
    """
    Set up default dashboards

    Args:
        kibana: KibanaDashboard instance

    Returns:
        Dict[str, str]: Dashboard IDs
    """
    # Create daily dashboard
    daily_result = kibana.create_dashboard(DAILY_DASHBOARD)
    daily_id = daily_result.get("id", "")

    # Create weekly dashboard
    weekly_result = kibana.create_dashboard(WEEKLY_DASHBOARD)
    weekly_id = weekly_result.get("id", "")

    return {"daily": daily_id, "weekly": weekly_id}
