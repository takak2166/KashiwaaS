"""
Kibana Dashboard Capture Module
Provides functionality for capturing Kibana dashboards using Selenium
"""

import os
import sys
import time
from typing import Dict, Optional

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.bot.alerter import AlertLevel, alert
from src.utils.config import config
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Check if running in a headless environment
HEADLESS_ENVIRONMENT = False


class KibanaCapture:
    """
    Kibana Dashboard Capture

    Captures screenshots of Kibana dashboards using Selenium
    """

    def __init__(
        self,
        kibana_host: Optional[str] = None,
        selenium_host: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        wait_time: int = 30,
    ):
        """
        Initialize Kibana Dashboard Capture

        Args:
            kibana_host: Kibana host URL
            selenium_host: Selenium host URL
            username: Kibana username (if authentication is enabled)
            password: Kibana password (if authentication is enabled)
            wait_time: Maximum wait time in seconds for page loading
        """
        self.kibana_host = kibana_host or config.kibana.host
        self.selenium_host = selenium_host or config.selenium_host
        self.username = username or config.kibana.username
        self.password = password or config.kibana.password
        self.wait_time = wait_time

        if not self.kibana_host:
            raise ValueError("Kibana host is required")
        if not self.selenium_host:
            raise ValueError("Selenium host is required")

        logger.info(f"Initialized Kibana Dashboard Capture with Kibana host: {self.kibana_host}")
        logger.info(f"Using Selenium host: {self.selenium_host}")

    def _create_driver(self) -> Optional[webdriver.Remote]:
        """
        Create Selenium WebDriver

        Returns:
            webdriver.Remote: Selenium WebDriver or None if creation fails
        """
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")

        try:
            driver = webdriver.Remote(command_executor=self.selenium_host, options=chrome_options)
            return driver
        except Exception as e:
            # Log full error with stack trace
            error_msg = f"Failed to create WebDriver: {e}"
            logger.error(error_msg)

            # Create a simplified error message for the alert (without stack trace)
            simple_error = str(e).split("\n")[0]  # Get only the first line
            alert_msg = f"Failed to create WebDriver: {simple_error}"

            # Send alert
            alert(
                message=alert_msg,
                level=AlertLevel.CRITICAL,
                title="CRITICAL: WebDriver Creation Failed - Kibana Dashboard Capture Impossible",
                details={
                    "selenium_host": self.selenium_host,
                    "error_type": e.__class__.__name__,
                },
            )

            # Exit program
            logger.critical("Exiting program due to WebDriver creation failure")
            sys.exit(1)

    def _login_if_needed(self, driver: webdriver.Remote) -> bool:
        """
        Login to Kibana if authentication is required

        Args:
            driver: Selenium WebDriver

        Returns:
            bool: True if login successful or not needed, False otherwise
        """
        if not self.username or not self.password:
            return True

        try:
            # Check if login form is present
            if len(driver.find_elements(By.ID, "username")) > 0:
                # Enter username
                username_input = driver.find_element(By.ID, "username")
                username_input.clear()
                username_input.send_keys(self.username)

                # Enter password
                password_input = driver.find_element(By.ID, "password")
                password_input.clear()
                password_input.send_keys(self.password)

                # Click login button
                login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                login_button.click()

                # Wait for login to complete
                WebDriverWait(driver, self.wait_time).until(EC.invisibility_of_element_located((By.ID, "username")))

                logger.info("Successfully logged in to Kibana")

            return True
        except Exception as e:
            logger.error(f"Failed to login to Kibana: {e}")
            return False

    def capture_dashboard(
        self,
        dashboard_id: str,
        output_path: str,
        time_range: Optional[str] = None,
        wait_for_render: int = 5,
    ) -> bool:
        """
        Capture screenshot of a Kibana dashboard

        Args:
            dashboard_id: Dashboard ID
            output_path: Output file path
            time_range: Time range (e.g., "last24hours", "last7days")
            wait_for_render: Time to wait for dashboard to render in seconds

        Returns:
            bool: True if successful, False otherwise
        """
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        # Create a placeholder image if we can't use Selenium
        if HEADLESS_ENVIRONMENT:
            try:
                # Try to import PIL for creating a placeholder image
                from PIL import Image, ImageDraw

                # Create a blank image
                img = Image.new("RGB", (1200, 800), color=(245, 245, 245))
                draw = ImageDraw.Draw(img)

                # Add text
                text = f"Kibana Dashboard: {dashboard_id}\nTime Range: {time_range or 'default'}\nPlaceholder Image"
                draw.text((50, 50), text, fill=(0, 0, 0))

                # Save the image
                img.save(output_path)
                logger.info(f"Created placeholder image at {output_path}")
                return True
            except ImportError:
                logger.warning("PIL not available for creating placeholder image")
            except Exception as e:
                logger.error(f"Failed to create placeholder image: {e}")

        driver = None
        try:
            # Create WebDriver - will exit program if it fails
            driver = self._create_driver()

            # Build dashboard URL
            dashboard_url = f"{self.kibana_host}/app/dashboards#/view/{dashboard_id}"
            if time_range:
                dashboard_url += f"?_g=(time:(from:now-{time_range},to:now))"

            # Navigate to dashboard
            logger.info(f"Navigating to dashboard: {dashboard_url}")
            driver.get(dashboard_url)

            # Login if needed
            if not self._login_if_needed(driver):
                return False

            # Wait for dashboard to load
            try:
                WebDriverWait(driver, self.wait_time).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".euiPanel"))
                )
            except TimeoutException:
                logger.error(f"Timeout waiting for dashboard {dashboard_id} to load")
                return False

            # Wait additional time for visualizations to render
            logger.info(f"Waiting {wait_for_render} seconds for visualizations to render")
            time.sleep(wait_for_render)

            # Take screenshot
            logger.info(f"Capturing screenshot to {output_path}")
            driver.save_screenshot(output_path)

            return True
        except Exception as e:
            # Log full error with stack trace
            error_msg = f"Failed to capture dashboard {dashboard_id}: {e}"
            logger.error(error_msg)

            # Create a simplified error message for the alert (without stack trace)
            simple_error = str(e).split("\n")[0]  # Get only the first line
            alert_msg = f"Failed to capture dashboard {dashboard_id}: {simple_error}"

            # Send alert
            alert(
                message=alert_msg,
                level=AlertLevel.ERROR,
                title="Dashboard Capture Failed",
                details={
                    "dashboard_id": dashboard_id,
                    "kibana_host": self.kibana_host,
                    "error_type": e.__class__.__name__,
                },
            )

            return False
        finally:
            # Close WebDriver
            if driver:
                try:
                    driver.quit()
                except Exception as e:
                    logger.error(f"Failed to quit WebDriver: {e}")

    def capture_visualization(
        self,
        visualization_id: str,
        output_path: str,
        time_range: Optional[str] = None,
        wait_for_render: int = 5,
    ) -> bool:
        """
        Capture screenshot of a Kibana visualization

        Args:
            visualization_id: Visualization ID
            output_path: Output file path
            time_range: Time range (e.g., "last24hours", "last7days")
            wait_for_render: Time to wait for visualization to render in seconds

        Returns:
            bool: True if successful, False otherwise
        """
        driver = None
        try:
            # Create WebDriver - will exit program if it fails
            driver = self._create_driver()

            # Build visualization URL
            viz_url = f"{self.kibana_host}/app/visualize#/edit/{visualization_id}"
            if time_range:
                viz_url += f"?_g=(time:(from:now-{time_range},to:now))"

            # Navigate to visualization
            logger.info(f"Navigating to visualization: {viz_url}")
            driver.get(viz_url)

            # Login if needed
            if not self._login_if_needed(driver):
                return False

            # Wait for visualization to load
            try:
                WebDriverWait(driver, self.wait_time).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".visEditor"))
                )
            except TimeoutException:
                logger.error(f"Timeout waiting for visualization {visualization_id} to load")
                return False

            # Wait additional time for visualization to render
            logger.info(f"Waiting {wait_for_render} seconds for visualization to render")
            time.sleep(wait_for_render)

            # Find visualization element
            try:
                viz_element = driver.find_element(By.CSS_SELECTOR, ".visEditor__visualization")

                # Take screenshot of visualization element
                logger.info(f"Capturing visualization screenshot to {output_path}")
                viz_element.screenshot(output_path)

                return True
            except Exception as e:
                logger.error(f"Failed to find visualization element: {e}")

                # Fallback to full page screenshot
                logger.info("Falling back to full page screenshot")
                driver.save_screenshot(output_path)

                return True
        except Exception as e:
            # Log full error with stack trace
            error_msg = f"Failed to capture visualization {visualization_id}: {e}"
            logger.error(error_msg)

            # Create a simplified error message for the alert (without stack trace)
            simple_error = str(e).split("\n")[0]  # Get only the first line
            alert_msg = f"Failed to capture visualization {visualization_id}: {simple_error}"

            # Send alert
            alert(
                message=alert_msg,
                level=AlertLevel.ERROR,
                title="Visualization Capture Failed",
                details={
                    "visualization_id": visualization_id,
                    "kibana_host": self.kibana_host,
                    "error_type": e.__class__.__name__,
                },
            )

            return False
        finally:
            # Close WebDriver
            if driver:
                driver.quit()

    def capture_dashboard_panels(
        self,
        dashboard_id: str,
        output_dir: str,
        time_range: Optional[str] = None,
        wait_for_render: int = 5,
    ) -> Dict[str, str]:
        """
        Capture screenshots of individual panels in a dashboard

        Args:
            dashboard_id: Dashboard ID
            output_dir: Output directory
            time_range: Time range (e.g., "last24hours", "last7days")
            wait_for_render: Time to wait for dashboard to render in seconds

        Returns:
            Dict[str, str]: Panel titles mapped to screenshot paths
        """
        driver = None
        try:
            # Create WebDriver - will exit program if it fails
            driver = self._create_driver()

            # Build dashboard URL
            dashboard_url = f"{self.kibana_host}/app/dashboards#/view/{dashboard_id}"
            if time_range:
                dashboard_url += f"?_g=(time:(from:now-{time_range},to:now))"

            # Navigate to dashboard
            logger.info(f"Navigating to dashboard: {dashboard_url}")
            driver.get(dashboard_url)

            # Login if needed
            if not self._login_if_needed(driver):
                return {}

            # Wait for dashboard to load
            try:
                WebDriverWait(driver, self.wait_time).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".euiPanel"))
                )
            except TimeoutException:
                logger.error(f"Timeout waiting for dashboard {dashboard_id} to load")
                return {}

            # Wait additional time for visualizations to render
            logger.info(f"Waiting {wait_for_render} seconds for visualizations to render")
            time.sleep(wait_for_render)

            # Find all panels
            panels = driver.find_elements(By.CSS_SELECTOR, ".embPanel")

            # Create output directory if it doesn't exist
            os.makedirs(output_dir, exist_ok=True)

            # Capture screenshots of each panel
            panel_screenshots = {}
            for i, panel in enumerate(panels):
                try:
                    # Get panel title
                    title_element = panel.find_element(By.CSS_SELECTOR, ".embPanel__title")
                    title = title_element.text.strip()

                    # Generate filename
                    safe_title = title.lower().replace(" ", "_").replace("/", "_")
                    filename = f"{safe_title}_{i}.png"
                    output_path = os.path.join(output_dir, filename)

                    # Take screenshot of panel
                    logger.info(f"Capturing panel '{title}' to {output_path}")
                    panel.screenshot(output_path)

                    panel_screenshots[title] = output_path
                except Exception as e:
                    logger.error(f"Failed to capture panel {i}: {e}")

            return panel_screenshots
        except Exception as e:
            # Log full error with stack trace
            error_msg = f"Failed to capture dashboard panels for {dashboard_id}: {e}"
            logger.error(error_msg)

            # Create a simplified error message for the alert (without stack trace)
            simple_error = str(e).split("\n")[0]  # Get only the first line
            alert_msg = f"Failed to capture dashboard panels for {dashboard_id}: {simple_error}"

            # Send alert
            alert(
                message=alert_msg,
                level=AlertLevel.ERROR,
                title="Dashboard Panels Capture Failed",
                details={
                    "dashboard_id": dashboard_id,
                    "kibana_host": self.kibana_host,
                    "error_type": e.__class__.__name__,
                },
            )

            return {}
        finally:
            # Close WebDriver
            if driver:
                driver.quit()
