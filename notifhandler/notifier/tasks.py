
from celery import shared_task

import time
import json
import requests
import logging
from .models import ElevatorInfo

logger = logging.getLogger(__name__)


@shared_task
def send_event(url, data, ip=None, agent_id=None, floor_id=None, send_notification=True):
    time.sleep(70)

    if ip and agent_id is not None and floor_id is not None:
        elevator_info, _ = ElevatorInfo.objects.get_or_create(ip_add=ip, elevator_id=agent_id, defaults={'floor_id': 0})
        elevator_info.floor_id = int(floor_id)
        elevator_info.save(update_fields=['floor_id'])
        logger.info("Updated ElevatorInfo after travel, IP: {0}, elevator_id: {1}, floor_id: {2}".format(
            ip, agent_id, floor_id))

    if not send_notification:
        logger.info("Skipping notify_agent callback as part of error simulation, URL: {0}, data: {1}".format(url, data))
        return

    logger.info("Sending to URL: {0}, data: {1}".format(url, data))
    res = requests.post(url, headers={'Content-type': 'application/json', 'Accept': 'application/json'},
                        data=json.dumps(data))
    logger.info("Response (POST request) status: {0}, response: {1}".format(res.status_code, res.text))

    # POST didn't work, retry with PUT method
    if res.status_code == 405:
        res = requests.put(url, headers={'Content-type': 'application/json', 'Accept': 'application/json'},
                           data=json.dumps(data))
        logger.info("Response (PUT request) status: {0}, response: {1}".format(res.status_code, res.text))
