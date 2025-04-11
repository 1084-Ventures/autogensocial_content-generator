import azure.functions as func
from azure.cosmos import CosmosClient
import logging
import os
from datetime import datetime, timezone
from typing import List, Dict, Any
from . import shared
import json
import random
import pytz

blueprint = func.Blueprint()

def _get_default_variable_values(template: Dict[str, Any]) -> Dict[str, str]:
    """Get default values for template variables."""
    try:
        variables = template.get('settings', {}).get('promptTemplate', {}).get('variables', [])
        default_values = {}
        for variable in variables:
            if 'name' in variable and 'values' in variable and variable['values']:
                default_values[variable['name']] = random.choice(variable['values'])
        return default_values
    except Exception as e:
        logging.error(f"Error getting default variable values: {str(e)}")
        return {}

def _get_templates_for_current_time() -> List[Dict[str, Any]]:
    """Get templates that should be executed at the current time."""
    try:
        # Get current UTC time
        current_utc = datetime.now(timezone.utc)
        current_day = current_utc.strftime('%A').lower()

        # Get templates from Cosmos DB
        cosmos_client = shared.init_cosmos_client()
        templates_container = cosmos_client.get_database_client(
            os.environ["COSMOS_DB_NAME"]
        ).get_container_client(os.environ["COSMOS_DB_CONTAINER_TEMPLATE"])

        query = """
        SELECT *
        FROM c
        WHERE c.metadata.isActive = true
        """
        templates = list(templates_container.query_items(
            query=query,
            enable_cross_partition_query=True
        ))

        matching_templates = []
        logging.info(f"Processing {len(templates)} active templates at {current_utc}")

        # Process each template
        for template in templates:
            try:
                # Validate template structure
                if not all(key in template for key in ['id', 'schedule', 'templateInfo']):
                    logging.warning(f"Template {template.get('id')} missing required fields")
                    continue

                schedule = template['schedule']
                if not all(key in schedule for key in ['daysOfWeek', 'timeSlots', 'maxPostsPerDay']):
                    logging.warning(f"Template {template.get('id')} schedule missing required fields")
                    continue

                # Convert schedule days to lowercase for case-insensitive comparison
                schedule_days = [day.lower() for day in schedule['daysOfWeek']]
                logging.debug(f"Template {template['id']} days: {schedule_days}, current day: {current_day}")
                
                if current_day not in schedule_days:
                    logging.debug(f"Template {template['id']} not scheduled for {current_day}")
                    continue

                # Check each time slot
                for slot in schedule['timeSlots']:
                    slot_time = current_utc
                    tz_name = slot.get('timezone', 'UTC')
                    
                    try:
                        if tz_name != 'UTC':
                            target_tz = pytz.timezone(tz_name)
                            slot_time = current_utc.astimezone(target_tz)
                    except pytz.exceptions.UnknownTimeZoneError:
                        logging.warning(f"Unknown timezone {tz_name} for template {template['id']}, using UTC")
                        continue

                    logging.debug(f"Checking slot time {slot_time.hour}:{slot_time.minute} against {slot['hour']}:{slot['minute']}")
                    
                    # Check if current time matches slot
                    if slot_time.hour == slot.get('hour') and slot_time.minute == slot.get('minute'):
                        # Verify we haven't exceeded daily post limit
                        posts_count = shared.get_todays_post_count(
                            templates_container,
                            template['templateInfo']['brandId'],
                            template['id']
                        )
                        
                        logging.debug(f"Template {template['id']} post count: {posts_count}, max: {schedule['maxPostsPerDay']}")
                        
                        if posts_count < schedule['maxPostsPerDay']:
                            matching_templates.append(template)
                            logging.info(f"Template {template['id']} matched for current time")
                            break
                        else:
                            logging.info(f"Template {template['id']} exceeded daily post limit")

            except Exception as e:
                logging.error(f"Error processing template {template.get('id')}: {str(e)}")
                continue

        return matching_templates

    except Exception as e:
        logging.error(f"Error getting templates for current time: {str(e)}")
        return []

@blueprint.timer_trigger(name="contentGenerationTimer",
                 schedule="0 */15 * * * *",  # Every 15 minutes
                 arg_name="timer")
def generate_scheduled_content(timer: func.TimerRequest) -> None:
    """Timer trigger to generate content based on scheduled templates."""
    if timer.past_due:
        logging.info('Timer is past due')
        return

    logging.info('Content generation timer trigger function started')
    try:
        templates = _get_templates_for_current_time()
        for template in templates:
            try:
                variables = _get_default_variable_values(template)
                result, status_code, error = shared.generate_content({
                    'templateId': template['id'],
                    'brandId': template['templateInfo']['brandId'],
                    'variableValues': variables
                }, is_timer=True)
                
                if status_code == 201:
                    logging.info(f"Generated content for template {template['id']}")
                else:
                    logging.error(f"Error generating content for template {template['id']}: {error}")
            except Exception as e:
                logging.error(f"Error generating content for template {template['id']}: {str(e)}")
    except Exception as e:
        logging.error(f"Error in timer trigger: {str(e)}")