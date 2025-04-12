import azure.functions as func
from shared import structured_logger
from shared.logger import log_function_call
from . import shared
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any
import json
import random
import pytz

blueprint = func.Blueprint()

@log_function_call(structured_logger)
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
        structured_logger.error(
            "Error getting default variable values",
            error=str(e),
            template_id=template.get('id')
        )
        return {}

@log_function_call(structured_logger)
def _get_templates_for_current_time() -> List[Dict[str, Any]]:
    """Get templates that should be executed at the current time."""
    try:
        # Get current UTC time
        current_utc = datetime.now(timezone.utc)
        current_day = current_utc.strftime('%A').lower()

        # Get templates from Cosmos DB
        cosmos_client = shared.init_cosmos_client()
        settings = shared.load_settings()
        templates_container = cosmos_client.get_database_client(
            settings.get('COSMOS_DB_NAME')
        ).get_container_client(settings.get('COSMOS_DB_CONTAINER_TEMPLATE'))

        # Get all active templates
        query = "SELECT * FROM c WHERE c.metadata.isActive = true"
        templates = list(templates_container.query_items(
            query=query,
            enable_cross_partition_query=True
        ))

        matching_templates = []
        structured_logger.info(
            f"Processing active templates",
            template_count=len(templates)
        )

        for template in templates:
            if not all(key in template for key in ['id', 'schedule', 'templateInfo']):
                continue

            schedule = template['schedule']
            if not all(key in schedule for key in ['daysOfWeek', 'timeSlots', 'maxPostsPerDay']):
                continue

            # Check if template should run today
            schedule_days = [day.lower() for day in schedule['daysOfWeek']]
            if current_day not in schedule_days:
                continue

            # Check time slots
            for slot in schedule['timeSlots']:
                slot_time = current_utc
                tz_name = slot.get('timezone', 'UTC')
                
                try:
                    if tz_name != 'UTC':
                        target_tz = pytz.timezone(tz_name)
                        slot_time = current_utc.astimezone(target_tz)
                except pytz.exceptions.UnknownTimeZoneError:
                    continue

                # Check if current time matches slot
                if slot_time.hour == slot.get('hour') and slot_time.minute == slot.get('minute'):
                    # Check daily post limit
                    posts_count = shared.get_todays_post_count(
                        templates_container,
                        template['templateInfo']['brandId'],
                        template['id']
                    )
                    
                    if posts_count < schedule['maxPostsPerDay']:
                        matching_templates.append(template)
                        break

        return matching_templates

    except Exception as e:
        structured_logger.error(
            "Error getting templates for current time",
            error=str(e)
        )
        return []

@blueprint.timer_trigger(schedule="0 */15 * * * *",  # Every 15 minutes
                       arg_name="timer")
@log_function_call(structured_logger)
def generate_scheduled_content(timer: func.TimerRequest) -> None:
    """Timer trigger to generate content based on scheduled templates."""
    structured_logger.set_correlation_id()
    
    try:
        if timer.past_due:
            structured_logger.warning('Timer trigger is past due')
            return

        structured_logger.info('Content generation timer trigger started')
        templates = _get_templates_for_current_time()
        processed_count = 0
        error_count = 0
        
        for template in templates:
            try:
                variables = _get_default_variable_values(template)
                result, status_code, error = shared.generate_content({
                    'templateId': template['id'],
                    'brandId': template['templateInfo']['brandId'],
                    'variableValues': variables
                }, is_timer=True)
                
                if status_code == 201:
                    processed_count += 1
                else:
                    error_count += 1
                    structured_logger.error(
                        "Error generating scheduled content",
                        template_id=template['id'],
                        error=error,
                        status_code=status_code
                    )
            except Exception as e:
                error_count += 1
                structured_logger.error(
                    "Error processing template",
                    template_id=template['id'],
                    error=str(e)
                )
                continue
        
        structured_logger.info(
            "Scheduler run complete",
            processed_count=processed_count,
            error_count=error_count
        )
    except Exception as e:
        structured_logger.error(
            "Error in timer trigger",
            error=str(e)
        )
    finally:
        structured_logger.clear_correlation_id()