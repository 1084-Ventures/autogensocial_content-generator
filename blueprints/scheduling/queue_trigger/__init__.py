import azure.functions as func
import json
import os
from datetime import datetime, timedelta
from azure.storage.queue import QueueClient
import pytz
from blueprints.orchestrator_blueprint import generate_content_orchestrator

def get_next_occurrence(day_of_week, hour, minute, timezone):
    from_zone = pytz.timezone(timezone)
    utc = pytz.utc
    now_utc = datetime.utcnow().replace(tzinfo=utc)
    now_local = now_utc.astimezone(from_zone)
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    target_day = days.index(day_of_week.lower())
    current_day = now_local.weekday()
    days_ahead = (target_day - current_day + 7) % 7
    # Always schedule for the next occurrence (never today)
    if days_ahead == 0:
        days_ahead = 7
    next_local = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)
    next_utc = next_local.astimezone(utc)
    return next_utc.replace(tzinfo=None)

def main(msg: func.QueueMessage) -> None:
    try:
        data = msg.get_body().decode('utf-8')
        payload = json.loads(data)
        class MockRequest:
            def __init__(self, json_data):
                self._json = json_data
                self.headers = {}
            def get_json(self):
                return self._json
        req = MockRequest({
            "templateId": payload.get("templateId"),
            "brandId": payload.get("brandId"),
            "variableValues": payload.get("variableValues", {})
        })
        generate_content_orchestrator(req)

        # --- Enqueue next scheduled run ---
        schedule = payload.get("schedule", {})
        template_id = payload.get("templateId")
        brand_id = payload.get("brandId")
        days_of_week = schedule.get("daysOfWeek", [])
        time_slots = schedule.get("timeSlots", [])
        for day in days_of_week:
            for slot in time_slots:
                hour = slot.get("hour", 8)
                minute = slot.get("minute", 0)
                timezone = slot.get("timezone", "UTC")
                next_run = get_next_occurrence(day, hour, minute, timezone)
                delay_seconds = int((next_run - datetime.utcnow()).total_seconds())
                if delay_seconds < 0:
                    continue
                queue_name = os.environ.get("SCHEDULER_QUEUE_NAME", "scheduled-content-queue")
                queue_conn_str = os.environ["AzureWebJobsStorage"]
                queue_client = QueueClient.from_connection_string(queue_conn_str, queue_name)
                next_payload = {
                    "templateId": template_id,
                    "brandId": brand_id,
                    "schedule": schedule
                }
                queue_client.send_message(json.dumps(next_payload), visibility_timeout=delay_seconds)
    except Exception as e:
        print(f"Error in queue trigger: {e}")
