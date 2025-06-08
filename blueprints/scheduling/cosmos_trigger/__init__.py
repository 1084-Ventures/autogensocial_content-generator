import azure.functions as func
import os
import json
from datetime import datetime, timedelta
from azure.storage.queue import QueueClient
import pytz

def get_next_occurrence(day_of_week, hour, minute, timezone):
    from_zone = pytz.timezone(timezone)
    utc = pytz.utc
    now_utc = datetime.utcnow().replace(tzinfo=utc)
    now_local = now_utc.astimezone(from_zone)
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    target_day = days.index(day_of_week.lower())
    current_day = now_local.weekday()
    days_ahead = (target_day - current_day + 7) % 7
    if days_ahead == 0 and (now_local.hour > hour or (now_local.hour == hour and now_local.minute >= minute)):
        days_ahead = 7
    next_local = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)
    next_utc = next_local.astimezone(utc)
    return next_utc.replace(tzinfo=None)

def main(documents: func.DocumentList) -> None:
    if documents:
        for doc in documents:
            try:
                template_id = doc.get("id")
                brand_id = doc.get("templateInfo", {}).get("brandId") or doc.get("brandId")
                schedule = doc.get("schedule", {})
                days_of_week = schedule.get("daysOfWeek", [])
                time_slots = schedule.get("timeSlots", [])
                if not (template_id and brand_id and days_of_week and time_slots):
                    continue
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
                        payload = {
                            "templateId": template_id,
                            "brandId": brand_id,
                            "schedule": schedule
                        }
                        queue_client.send_message(json.dumps(payload), visibility_timeout=delay_seconds)
            except Exception as e:
                print(f"Error scheduling for doc: {e}")
