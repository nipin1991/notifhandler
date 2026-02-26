
from celery import shared_task

import time
import json
import requests
import logging

logger = logging.getLogger(__name__)


@shared_task
def send_event(url, data):
    time.sleep(70)
    logger.info("Sending to URL: {0}, data: {1}".format(url, data))
    res = requests.post(url, headers={'Content-type': 'application/json', 'Accept': 'application/json'},
                        data=json.dumps(data))
    logger.info("Response (POST request) status: {0}, response: {1}".format(res.status_code, res.text))

    # POST didn't work, retry with PUT method
    if res.status_code == 405:
        res = requests.put(url, headers={'Content-type': 'application/json', 'Accept': 'application/json'},
                           data=json.dumps(data))
        logger.info("Response (PUT request) status: {0}, response: {1}".format(res.status_code, res.text))
