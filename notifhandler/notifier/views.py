# -*- coding: utf-8 -*-


import json
import time
import random
import logging
import collections
from uuid import uuid4
from datetime import datetime
from importlib import import_module

from django.conf.urls import url
from django.conf import settings
from django.db import IntegrityError, connection
from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required, user_passes_test

from lib.butlerFunctions import ButlerFunctions
from .models import NotifAuth, AuthToken, NotifData, NotifURL, ElevatorInfo, IPAddressNotifData
from .tasks import send_event
from conf.sbs_config import PLCConfig as plc
from django.template import loader
from django.template.exceptions import TemplateDoesNotExist
from django import http

# Get an instance of a logger
logger = logging.getLogger(__name__)


def group_check(user):
    return user.groups.filter(name='internal_GOR').exists()


def user_group_check(user, group_name):
    return user.groups.filter(name__in=group_name)


def convert(data):
    if isinstance(data, str):
        return str(data)
    elif isinstance(data, collections.Mapping):
        return dict(list(map(convert, iter(data.items()))))
    elif isinstance(data, collections.Iterable):
        return type(data)(list(map(convert, data)))
    else:
        return data


@csrf_exempt
def delayed_request(timeout=60):
    # sleep for 60 sec(default) before sending the response
    # to be used in specific paste function (used in paste1)
    time.sleep(timeout)


def paste_main(request, paste_url_name):
    """
    Subscribe to notifications and POST notifications using multiple paste URLs
    Store incoming notifs to postgres DB
    :return: JsonResponse 200 with whole data
    """

    logger.info("ViewFunction : paste_main")
    if request.method == 'GET':
        return JsonResponse("GET request not supported for this URL.", status=405)

    elif request.method == 'POST':
        try:
            custom_headers = {}
            for key, val in list(request.META.items()):
                if key.startswith('HTTP_X') or key in ["gornotificationtimestamp", "wmt-correlationid"]:
                    custom_headers[key] = val

            ip = request.META.get('REMOTE_ADDR')
            notif_type = request.META.get('HTTP_X_PATTERN')
            logger.info("Received notification request: {0} from {1}".format(notif_type, ip))
            notif_json = json.loads(request.body.decode('utf-8'))
            state_status, esr_id = None, None
            if notif_type in ('service-request-pick-notification', 'service-request-put-notification',
                              'packing_box_association', 'service-request-bulk-modify-success'):
                logger.debug(f"Request type is either PUT or PICK, type: {notif_type}. "
                             f"Fetching state, status from notification")
                try:
                    esr_id = notif_json['notification_data']['externalServiceRequestId']
                    logger.info(f"Fetched esr_id: {esr_id} from notification")
                except (KeyError, ValueError) as e:
                    logger.error(f"Exception: {e}\n ERROR fetching in esr_id in notification, "
                                 f"where notification type={notif_type}")
                try:
                    state_status = {'state': notif_json['notification_data']['state'],
                                    'status': notif_json['notification_data']['status']}
                    logger.info(f"Fetched state_status from notification: {state_status}")
                except (KeyError, ValueError) as e:
                    logger.error(f"Exception: {e}\n ERROR fetching in state, status in notification, "
                                 f"where notification type={notif_type}")

            elif notif_type == 'tag_update_information':
                esr_id = notif_json['notification_data']['request_id']

            notif_type = {'notif_type': request.META.get('HTTP_X_PATTERN'), 'ip_add': ip}
            if state_status:
                notif_type.update(state_status)

            try:
                ip_add_rec = IPAddressNotifData.objects.get(ip_address=ip)
            except IPAddressNotifData.DoesNotExist:
                ip_add_rec = IPAddressNotifData.objects.create(ip_address=ip)
                ip_add_rec.save()

            rec = NotifData(ip_add=ip_add_rec, notif_type=notif_type, paste_url=paste_url_name,
                            headers=custom_headers, data=notif_json, esr_id=esr_id)
            logger.info("Saved NotifData record with ID: {0}".format(rec.auto_increment_id))
            rec.save()
            connection.close()  # this prevents from leaving open DB connections from django

            ret_data = {"status": 200, "data": "Success, saved {0} notification".format(notif_type)}
        except Exception as e:
            logger.error("Something unexpected happened, Exception:\n{0}".format(e))
            ret_data = {"status": 500, "data": "Failed"}
        return ret_data


# remember LOGIN_URL has to be defined in settings.py
@csrf_exempt
@login_required()
def create_url(request):
    """
    Create an URL endpoint, to be added to subscribers. Required by sorter team
    :param request: URL endpoint, Response JSON
    :return: Render create URL page
    """

    logger.info("ViewFunction : create_url")
    if request.method != 'GET':
        return JsonResponse("Only GET method is supported for this URL.", status=405, safe=False)

    msg = ''
    if request.GET.get('endpoint'):
        url_endpoint = request.GET['endpoint']
        response_content = request.GET['response']
        logger.info("Create URL, endpoint: {0}, response JSON: {1}".format(url_endpoint, response_content))
        try:
            res_content_json = json.loads(response_content)
            url_rec = NotifURL(url_pattern=url_endpoint, response=res_content_json, created_by=request.user.username)
            url_rec.save()
            msg = "URL created Successfully."
            urls = import_module(settings.ROOT_URLCONF)
            urls.urlpatterns.append(url('^' + url_endpoint + '$', sorter_generic_view))
            logger.info("NotifURL created successfully, ID: {0}".format(url_rec.id))

        except ValueError:
            logger.warning("Invalid JSON content in response.")
            msg = "Invalid JSON content in response."
        except IntegrityError:
            logger.warning("IntegrityError, URL: {0} already exists.")
            msg = "ERROR: URL: {0} already exists."

    logger.info("Return from create_url, msg: {0}".format(msg))
    return render(request, 'create_url.html', {'msg': msg})


@csrf_exempt
def sorter_generic_view(request):
    if request.method == 'POST':
        url_name = request.path_info.strip('/')
        logger.info("ViewFunction : sorter_generic_view, URL: {0}".format(request.path_info))
        url_db_rec = NotifURL.objects.get(url_pattern=url_name)
        logger.info("URL response to be returned: {0}".format(url_db_rec.response))
        return JsonResponse(url_db_rec.response, status=200, safe=False)
    else:
        logger.warning("ViewFunction: sorter_generic_view. Invalid request method: {0} received".format(request.method))
        return JsonResponse("Only GET method is supported for this URL.", status=405, safe=False)


@csrf_exempt
@login_required()
def view_url(request):
    logger.info("ViewFunction : view_url")
    if request.method == 'GET':
        data = list(NotifURL.objects.all().values())
        logger.info("Returning all data to html, len: {0}".format(len(data)))
        return render(request, 'view_url.html', {'data': data})
    else:
        logger.warning("Invalid method received for view_url")
        return JsonResponse("Only GET method is supported for this URL.", status=405, safe=False)


@csrf_exempt
@login_required()
def delete_url(request):
    logger.info("ViewFunction : delete_url")
    if request.method == 'POST':
        url_id = request.POST.get()
        logger.info("NotifURL record delete request received ID: {0}".format(url_id))
        data = list(NotifURL.objects.all().values())
        return render(request, 'view_url.html', {'data': data, 'msg': 'URL deleted successfully'})
    else:
        logger.warning("Invalid method received for delete_url")
        return JsonResponse("Only GET method is supported for this URL.", status=405, safe=False)


@csrf_exempt
def paste(request):
    """
    Subscribe to notifications and POST notifications using /paste URL
    Store incoming notifs to postgres DB
    :return: JsonResponse 200 with whole data
    """
    logger.info("ViewFunction : paste")
    res = paste_main(request, "paste")
    connection.close()  # this prevents from leaving open DB connections from django
    return JsonResponse(res["data"], status=res["status"], safe=False)


@csrf_exempt
def paste1(request):
    """
    Subscribe to notifications and POST notifications using /paste1 URL
    :return: JsonResponse 200 with whole data
    """
    logger.info("ViewFunction : paste1")
    res = paste_main(request, "paste1")
    connection.close()  # this prevents from leaving open DB connections from django
    return JsonResponse(res["data"], status=res["status"], safe=False)


@csrf_exempt
def paste_verte(request):
    """
    URL created to serve only siMutant notifications for Verte US client
    Subscribe to notifications and POST notifications using /paste_verte URL
    :return: JsonResponse 200 with whole data
    """
    logger.info("ViewFunction : paste_verte")
    res = paste_main(request, "paste_verte")
    connection.close()  # this prevents from leaving open DB connections from django
    return JsonResponse(res["data"], status=res["status"], safe=False)


@csrf_exempt
def paste_sodimac(request):
    """
    URL created to serve only siMutant notifications for Sodimac Colombia client
    Subscribe to notifications and POST notifications using /paste_sodimac URL
    :return: JsonResponse 200 with whole data
    """
    logger.info("ViewFunction : paste1")
    res = paste_main(request, "paste1")
    connection.close()  # this prevents from leaving open DB connections from django
    return JsonResponse(res["data"], status=res["status"], safe=False)


@csrf_exempt
def sorter(request):
    """
    paste URL for sorter
    """

    logger.info("ViewFunction : sorter")
    res = paste_main(request, "sorter")
    connection.close()  # this prevents from leaving open DB connections from django
    return JsonResponse(res["data"], status=res["status"], safe=False)


@csrf_exempt
def paste_with_auth(request):
    """
    Subscribe to the notification URL with the Authentication-Token in header
    """
    logger.info("ViewFunction : paste_with_auth")

    if request.method == 'GET':
        return JsonResponse("GET method not supported for this URL.", status=405, safe=False)
    elif request.method == 'POST':
        logger.info("All Headers : {0}".format(request.META))
        auth_token = request.META.get('HTTP_AUTHORIZATION', None)
        if auth_token:

            # token is stored without the Bearer in DB,
            # when receiving the calls, we receive - "Authorization": "Bearer eg4ergbtgrefwf42"

            auth_token_rec = AuthToken.objects.get(token=auth_token.split("Bearer ")[1])
            if auth_token_rec:
                logger.info("Successfully authenticated using auth token.")
                res = paste_main(request, "pasteauth")
                return JsonResponse(res["data"], status=res["status"], safe=False)
            else:
                logger.info("Unauthorized, using auth token, return 401 JsonResponse")
                return JsonResponse("Unauthorized.", status=401, safe=False)
        else:
            logger.info("Unauthorized, no Authentication-Token supplied, return 401 JsonResponse")
            return JsonResponse("Unauthorized, no Authorization in header.", status=401, safe=False)


@csrf_exempt
@login_required()
def notifauth(request):
    """
    Authentication system API, using username, password and siteid
    :return: JsonResponse with token if successful
    """
    logger.info("ViewFunction : notifauth")

    if request.method == 'GET':
        return JsonResponse("GET request not supported for this URL.", status=405, safe=False)

    elif request.method == 'POST':
        body_unicode = request.body.decode('utf-8')
        body_data = json.loads(body_unicode)

        # AA, below lines commented, used when input params are specified in url-encoded form rather than json

        # for row in body_unicode.split("&"):
        #     body_data[row.split("=")[0]] = urllib2.unquote(row.split("=")[1])
        # logger.info("Final body_data received: {0}".format(body_data))
        # logger.info("Received auth request for username: {0}, grant_type: {1}".format(body_data["username"],
        #                                                                               body_data["grant_type"]))
        try:
            notif_query_data = NotifAuth.objects.get(client='xpo', user=body_data["username"],
                                                     passwd=str(body_data["password"]), siteid="verizon")
        except NotifAuth.DoesNotExist:
            return JsonResponse("Username/password/siteid not found.", status=404, safe=False)
        else:
            token_query_data = list(AuthToken.objects.filter(userid=notif_query_data.auto_increment_id).values())
            if token_query_data:
                token_hex = token_query_data[0]["token"]
            else:
                token_hex = uuid4().hex
                token_rec = AuthToken(userid=notif_query_data, token=token_hex)
                token_rec.save()
            response = JsonResponse({"Token": token_hex, "Roles": ["GreyOrangeRole"]}, status=200, safe=False)
            connection.close()  # this prevents from leaving open DB connections from django
            return response


@csrf_exempt
@login_required()
@user_passes_test(group_check)
def view(request):
    """
    View the whole data on UI using /view URL, changed to 5 days
    :return: Render complete data with a template
    """

    logger.info("ViewFunction : view")
    if request.method != 'GET':
        return JsonResponse("Only GET method is supported for this URL.", status=405)

    # AA - 12 Sep 2019, below code commented for now, sorter team is not using the dynamic URLs creations

    # every user is either a member of internal_GOR or external client groups
    # this was done as requested by sorter team,
    # they want to see the notifications of their subscribed URLs only (dynamically created)

    # user_all_groups = [group.name for group in request.user.groups.all()]
    # logger.info("username: {0}, groups assigned to user: {1}".format(request.user.username,
    #                                                                  request.user.groups.values_list()))

    # assigned_groups = [name for name in user_all_groups if name not in ['internal_GOR']]
    # group_list = user_group_check(request.user, assigned_groups)
    # logger.info("URL list to be used for filtering the NotifData: {0}".format(group_list))
    #
    # if group_list:
    #     subscribe_url_list = [group.name for group in group_list]
    #     query_data = NotifData.objects.filter(paste_url__in=subscribe_url_list).order_by('-created_on')[:500].values()
    # else:
    #     query_data = NotifData.objects.all().order_by('-created_on')[:500].values()

    query_data = NotifData.objects.all().order_by('-auto_increment_id')[:100].values()
    connection.close()  # this prevents from leaving open DB connections from django
    for record in query_data:
        record["data"] = json.dumps(record["data"])
        record["notif_type"] = json.dumps(record["notif_type"])
        record["headers"] = json.dumps(record["headers"])
    return render(request, 'viewdata.html', {'data': query_data})


@csrf_exempt
@login_required()
@user_passes_test(lambda u: u.groups.filter(name='verte').exists())
def notif_verte(request):
    """ View by ip implementation for notif view URL for Verte - simutant """

    logger.info("ViewFunction : notif_verte")
    request.GET._mutable = True
    request.GET.__setitem__('ip', '139.162.32.168')
    request.GET.__setitem__('url', 'paste_verte')
    request.GET._mutable = False
    res = view_by_ip(request)
    return res


@csrf_exempt
@login_required()
@user_passes_test(lambda u: u.groups.filter(name='sodimac').exists())
def notif_sodimac(request):
    """ View by ip implementation for notif view URL for Sodimac Colombia - simutant """

    logger.info("ViewFunction : notif_sodimac")
    request.GET._mutable = True
    request.GET.__setitem__('ip', '139.162.32.168')
    request.GET.__setitem__('url', 'paste_sodimac')
    request.GET._mutable = False
    res = view_by_ip(request)
    return res


@csrf_exempt
@login_required()
def view_by_ip(request):
    """
    Filter the data for specified IP using /view_by_ip URL
    :param request: IP address
    :return: Render data with a template
    """

    logger.info("ViewFunction : view_by_ip")
    if request.method != 'GET':
        return JsonResponse("Only GET method id supported for this URL.", status=405)

    ip_addr = request.GET['ip']
    logger.info("View by IP: {0}".format(ip_addr))
    try:
        ip_rec = IPAddressNotifData.objects.get(ip_address=ip_addr)
        query_data = NotifData.objects.filter(ip_add=ip_rec).order_by('-auto_increment_id')[:100].values()
    except IPAddressNotifData.DoesNotExist:
        logger.error("IP Address records not found: {0}".format(ip_addr))
        query_data = []

    connection.close()  # this prevents from leaving open DB connections from django
    for record in query_data:
        record["data"] = json.dumps(record["data"])
        record["notif_type"] = json.dumps(record["notif_type"])
        record["headers"] = json.dumps(record["headers"])
    return render(request, 'viewdata.html', {'data': query_data})


@csrf_exempt
@login_required()
@user_passes_test(group_check)
def view_inventory(request):
    """
    Return inventory details for a system (SKU and quantity)
    :param request: butler IP, platform IP
    :return: Render inventory data for that IP, list of SKUs with quantity
    """

    logger.info("ViewFunction : view_inventory")
    if request.method != 'GET':
        return JsonResponse("Only GET method is supported for this URL.", status=405)

    inventory, total_inv_count = {}, 0
    if request.GET.get('platform') and request.GET.get('butler'):
        butler_ip = request.GET['butler']
        platform_ip = request.GET['platform']

        logger.info(f"View inventory, Platform IP: {platform_ip}, Butler IP: {butler_ip}")

        butler = ButlerFunctions()
        inventory = butler.get_all_inventory_details(butler_ip, platform_ip, username="admin", password="apj0702",
                                                     mdm_type=False, return_uid=True)
        logger.info(f"Inventory records found: {inventory}")
        if inventory:
            total_inv_count = sum([sku_qty[1] for sku_qty in inventory.values()])

    return render(request, 'inventory.html', {'data': inventory, 'inv_count': total_inv_count})


@csrf_exempt
def agent_status(request):
    """
    :return: JsonResponse, always True for PPP & ARA, with status for ELEVATOR
    """

    logger.info("ViewFunction: agent_status")
    if request.method != 'GET':
        return JsonResponse("Only GET method is supported for this URL.", status=405, safe=False)

    agent_type = request.GET['agent_type']
    status = request.GET['status']
    if agent_type in ('PPP', 'ARA'):
        return JsonResponse({"status_list": [{"value": True}]}, status=200, safe=False)

    if agent_type == 'ELEVATOR':

        # value=0 means when RESET the lift
        if status == 'GETCURRENTFLOOR':
            return JsonResponse({"status_list": [{"value": 0}, {"status": status}]}, status=200, safe=False)

        # LIFTSTATUS, value=2 means lift is in auto mode
        if status == 'LIFTSTATUS':
            return JsonResponse({"status_list": [{"value": 2}, {"status": status}]}, status=200, safe=False)

        if status == 'GETCOMPLETEDATA':
            agent_id = request.GET['agent_id']
            ip = request.META['REMOTE_ADDR']
            try:
                elevator_info = ElevatorInfo.objects.get(ip_add=ip, elevator_id=agent_id)
            except ElevatorInfo.DoesNotExist:
                elevator_info = ElevatorInfo(ip_add=ip, elevator_id=agent_id, floor_id=0)
                elevator_info.save()
            current_floor = elevator_info.floor_id
            if request.path.strip() == '/agent_event_big':
                elevator_floor_config = plc.FOUR_FLOOR_ELEVATOR
            else:
                elevator_floor_config = plc.TWO_FLOOR_ELEVATOR

            random_floor = random.choice(list(elevator_floor_config.keys()))
            connection.close()  # this prevents from leaving open DB connections from django
            return JsonResponse({"reached_floor_id": int(current_floor), "current_floor_id": random_floor,
                                 "elevator_status": 2, "elevator_id": agent_id}, status=200, safe=False)
    return JsonResponse("Invalid request", status=400, safe=False)


@csrf_exempt
def agent_event(request):
    """
    OPC client -> server -> PLC -> H/W communication simulation for elevator like events
    e.g. Butler server calls this API with Goto floor event, we return Reached floor to butler notify_agent
    """

    logger.info("ViewFunction: agent_event")
    if request.method not in ('POST', 'PUT'):
        return JsonResponse("Only POST or Put method is supported for this URL.", status=405, safe=False)

    # currently 2 maps are supported, based on PLCConfig defined in sbs_config
    if request.path.strip() == '/agent_event_big':
        elevator_floor_config = plc.FOUR_FLOOR_ELEVATOR
    else:
        elevator_floor_config = plc.TWO_FLOOR_ELEVATOR

    fields_required, not_present = ['agent_id', 'agent_type', 'event', 'value'], []
    ip = request.META['REMOTE_ADDR']
    logger.info("IP: {0}, request.path: {1}, request POST: {2}, elevator config: {3}".format(
        ip, request.path, request.body, elevator_floor_config))

    req_data = json.loads(request.body)
    for field in fields_required:
        if field not in req_data:
            not_present.append(field)

    # fields_required are all mandatory keys in a request
    if not_present:
        return JsonResponse("Insufficient data, Missing keys: {0}".format(not_present), status=422, safe=False)

    events = {
        "GOTOFLOOR": "REACHEDFLOOR",
        "READYFOROPERATOR": "OK"
    }

    agent_id = req_data['agent_id']     # elevator_id / PPP ID
    agent_type = req_data['agent_type']     # ELEVATOR / PPP / ARA
    event = req_data['event'].split('_')[-1]  # event_name --> READYFORBOT
    floor_id = 0

    # we receive the barrier id from butler_server,
    # resolve the floor id from barrier id from PLCConfig (conf/sbs_config.py)

    if agent_type == 'ELEVATOR' and req_data['value']:
        event_value = req_data['value']
        for floor, barriers in list(elevator_floor_config.items()):
            if event_value in barriers:
                floor_id = floor

    response = {
        "error": False,
        "error_description": "None",
        "msg:": "Event Trigger Success",
        "agent_id": agent_id,
        "event": event
    }

    if agent_type == 'ARA':
        response = {"value": True}

    if event == 'GOTOFLOOR':
        res_json = {"agent_id": agent_id, "agent_type": agent_type, "event": events[event], "value": floor_id}
        response["value"] = floor_id

        # maintain the elevator info for each machine
        # store/update the elevator info based on calls from butler server
        try:
            elevator_info = ElevatorInfo.objects.get(ip_add=ip, elevator_id=agent_id)
            current_floor = elevator_info.floor_id
            logger.info("IP: {0}, elevator id: {1}, current floor: {2}".format(ip, agent_id, current_floor))

            if int(current_floor) == int(response['value']):
                logger.info("IP: {0}, current floor: {1} is same as GOTO floor: {2}. Not sending REACHEDFLOOR.".format(
                    ip, int(current_floor), int(response['value'])))
                return JsonResponse(response, status=200, safe=False)
            elevator_info.floor_id = int(floor_id)

        except ElevatorInfo.DoesNotExist:
            logger.info("IP: {0}, ElevatorInfo does not exist".format(ip))
            elevator_info = ElevatorInfo(ip_add=ip, elevator_id=agent_id, floor_id=floor_id)

        elevator_info.save()
        logger.info("Successfully saved ElevatorInfo, IP: {0}, elevator_id: {1}, floor_id: {2}".format(
            ip, agent_id, floor_id))

        # send REACHEDFLOOR
        #time.sleep(68)
        #logger.info("slept for 68 sec , IP: {0}, elevator_id: {1}, floor_id: {2}".format(ip, agent_id, floor_id))
        api_uri = 'http://{0}:8181/api/notify_agent'.format(ip)

        # some ad-hoc changes done for Saurabh's setup, to simulate errors for some calls
        if ip == '192.168.8.236':
            request_count = random.randint(1, 101)
            if request_count % 50 == 0:
                res_json['value'] = 0
                logger.info("Request Count:{0} is divisible by 50, Hence sending Floor ID as 0".format(request_count))
                send_event.delay(api_uri, res_json)
            elif request_count % 50 == 25:
                logger.info("Request Count:{0} is divisible by 25, Hence sending Nothing".format(request_count))
                pass
            else:
                logger.info("Request Count:{0} is normal case, Hence sending the correct REACHEDFLOOR".format(request_count))
                api_uri = 'http://{0}:8181/api/notify_agent'.format(ip)

        send_event.delay(api_uri, res_json)

    connection.close()  # this prevents from leaving open DB connections from django
    return JsonResponse(response, status=200, safe=False)


@csrf_exempt
def get_by_exid(request):
    """
    Query in the DB to return matching notifs, initially meant for Pick notifs
    :param request: IP Address, Notif Type, externalServiceRequestId
    :return: List of notifications matching above 3 params
    """

    logger.info(f"Function:get_by_exid, request: {request.method}, {request.body}")
    if request.method == 'POST':
        logger.info("Received get_by_exid request, data:{0}".format(request.body))
        request_data = json.loads(request.body)
        ip_add = request_data['ip']
        esr_id = request_data.get('esr_id', 'dummy_invoice_id')
        start_time = request_data.get('stime', None)
        end_time = request_data.get('etime', None)
        headers = request_data.get('headers', None)
        notification_type = request_data.get('notification_type', None)

        # filter the matching rows
        if esr_id == 'dummy_invoice_id':
            if start_time and end_time:
                logger.info("querying, start_time:{0}, end_time:{1}".format(datetime.strptime(
                    start_time, "%Y-%m-%d %H:%M:%S.%f"), datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S.%f")))
                query_data = NotifData.objects.filter(
                    ip_add=ip_add, created_on__lte=datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S.%f"),
                    created_on__gte=datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S.%f"))
            elif notification_type:
                logger.info("querying in NotifData, notification_type: {0}".format(notification_type))
                query_data = NotifData.objects.filter(
                    ip_add=ip_add, notif_type__notif_type=notification_type)
            else:
                query_data = NotifData.objects.filter(ip_add=ip_add)
        else:
            if start_time and end_time:
                logger.info("querying, start_time:{0}, end_time:{1}".format(datetime.strptime(
                    start_time, "%Y-%m-%d %H:%M:%S.%f"), datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S.%f")))
                query_data = NotifData.objects.filter(
                    ip_add=ip_add, esr_id=esr_id, created_on__lte=datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S.%f"),
                    created_on__gte=datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S.%f"))
            else:
                query_data = NotifData.objects.filter(ip_add=ip_add, esr_id=esr_id)

        logger.info("notif_data:{0}".format(query_data))
        if headers:
            notifications = [(record['data'], record['headers']) for record in list(query_data.values())]
        else:
            notifications = [record['data'] for record in list(query_data.values())]
        logger.info(f"Found notifications: {notifications}")

        connection.close()  # this prevents from leaving open DB connections from django
        return JsonResponse(notifications, status=200, safe=False)
    else:
        return JsonResponse("Invalid request method received. Only POST method is supported.",
                            status=405, safe=False)


@csrf_exempt
def signup(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('/account')
    else:
        form = UserCreationForm()

        args = {'form': form}
        return render(request, 'core/signup.html', args)


@csrf_exempt
def account_page(request):
    return HttpResponse('success')


@csrf_exempt
def paste_error(request, template_name='.html'):
    """
    500 error handler.

    Templates: :template:`core/signup.html`
    Context: None
    """

    error_html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
        </head>
        <body>
        Internal Server Error &nbsp; &nbsp; (500).
        </body>
        </html>
    """
    try:
        loader.get_template(template_name)
    except TemplateDoesNotExist:
        return http.HttpResponseServerError(error_html)


@csrf_exempt
def runrobo(request):
    logger.info("ViewFunction : runrobo")
    if request.method == 'POST' and request.POST.get('butler'):
        from runrobo import Runrobo

        # return HttpResponse(str(out))

    logger.info("ViewFunction : runrobo")
    return render(request, 'runrobo.html')
