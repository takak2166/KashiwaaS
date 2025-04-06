#!/usr/bin/env python3
import os
import argparse
import logging
from pathlib import Path
from typing import Dict, Any

import jinja2
import requests
from dotenv import load_dotenv

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_env() -> Dict[str, Any]:
    """Load environment variables"""
    load_dotenv()
    required_env_vars = [
        'SLACK_CHANNEL_NAME',
        'KIBANA_HOST'
    ]
    
    env = {}
    for var in required_env_vars:
        value = os.getenv(var)
        if not value:
            raise ValueError(f"Environment variable {var} is not set")
        env[var] = value
    
    return env

def render_template(template_path: Path, env: Dict[str, Any]) -> str:
    """Render template with environment variables"""
    template_loader = jinja2.FileSystemLoader(searchpath=template_path.parent)
    template_env = jinja2.Environment(loader=template_loader)
    template = template_env.get_template(template_path.name)
    return template.render(**env)

def import_kibana_object(
    kibana_host: str,
    file_path: Path,
    overwrite: bool = False
) -> bool:
    """Import objects to Kibana"""
    url = f"{kibana_host}/api/saved_objects/_import"
    params = {'overwrite': 'true'} if overwrite else {}
    
    with open(file_path, 'rb') as f:
        files = {'file': f}
        response = requests.post(
            url,
            params=params,
            files=files,
            headers={'kbn-xsrf': 'true'}
        )
    
    if response.status_code == 200:
        result = response.json()
        if result.get('success'):
            logger.info(f"Import successful: {result.get('successCount')} objects")
            return True
        else:
            logger.error(f"Import failed: {result.get('errors')}")
            return False
    else:
        logger.error(f"API request failed: {response.status_code} - {response.text}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Import Kibana objects')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing objects')
    args = parser.parse_args()
    
    try:
        # Load environment variables
        env = load_env()
        
        # Set variables
        env['index_pattern_id'] = f"slack-{env['SLACK_CHANNEL_NAME']}"
        env['index_pattern_title'] = env['index_pattern_id']
        env['lens_id'] = f"tagcloud-{env['SLACK_CHANNEL_NAME']}"
        env['lens_title'] = "tag cloud"
        env['layer_id'] = f"layer-{env['SLACK_CHANNEL_NAME']}"
        env['dashboard_id'] = f"{env['SLACK_CHANNEL_NAME']}-weekly"
        env['dashboard_title'] = f"{env['SLACK_CHANNEL_NAME']}'s Dashboard"
        env['dashboard_description'] = f"message statistics dashboard of {env['SLACK_CHANNEL_NAME']}"
        
        # Set template directory
        templates_dir = Path(__file__).parent.parent / 'kibana' / 'templates'
        
        # Import order
        import_order = [
            ('index_pattern.ndjson.j2', 'Index pattern'),
            ('lens.ndjson.j2', 'Lens'),
            ('dashboard.ndjson.j2', 'Dashboard')
        ]
        
        # Import each object
        for template_file, object_type in import_order:
            template_path = templates_dir / template_file
            if not template_path.exists():
                logger.error(f"Template file not found: {template_path}")
                continue
            
            # Render template
            rendered_content = render_template(template_path, env)
            
            # Save to temporary file
            temp_file = Path(f"temp_{template_file.replace('.j2', '')}")
            try:
                with open(temp_file, 'w') as f:
                    f.write(rendered_content)
                
                # Import to Kibana
                logger.info(f"Starting import of {object_type}")
                success = import_kibana_object(
                    env['KIBANA_HOST'],
                    temp_file,
                    args.overwrite
                )
                
                if success:
                    logger.info(f"Import of {object_type} completed")
                else:
                    logger.error(f"Import of {object_type} failed")
                    break
            finally:
                # Clean up temporary file
                if temp_file.exists():
                    temp_file.unlink()
    
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main()) 