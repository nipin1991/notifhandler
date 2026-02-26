# -*- coding: utf-8 -*-

from django.contrib.postgres.fields import JSONField
from django.db import models


class IPAddressNotifData(models.Model):
    ip_address = models.GenericIPAddressField(primary_key=True)


class NotifData(models.Model):
    auto_increment_id = models.AutoField(primary_key=True)
    created_on = models.DateTimeField(auto_now_add=True, blank=True)
    ip_add = models.ForeignKey(IPAddressNotifData, on_delete=models.CASCADE)
    notif_type = JSONField(null=True, blank=True)
    paste_url = models.CharField(max_length=30, null=True)
    headers = JSONField(null=True, blank=True)
    data = JSONField()
    esr_id = models.CharField(max_length=255, null=True, blank=True)


class NotifAuth(models.Model):
    auto_increment_id = models.AutoField(primary_key=True)
    client = models.CharField(max_length=20, null=True)
    user = models.CharField(max_length=30)
    passwd = models.CharField(max_length=30)
    siteid = models.CharField(max_length=20)
    created = models.DateTimeField(auto_now_add=True)


class AuthToken(models.Model):
    auto_increment_id = models.AutoField(primary_key=True)
    userid = models.ForeignKey(NotifAuth, on_delete=models.PROTECT)
    token = models.CharField(max_length=40)
    created = models.DateTimeField(auto_now_add=True)


class NotifURL(models.Model):
    id = models.AutoField(primary_key=True)
    url_pattern = models.URLField(max_length=30, unique=True)
    response = JSONField()
    created_by = models.CharField(max_length=100)
    created_on = models.DateTimeField(auto_now_add=True)


class ElevatorInfo(models.Model):
    ip_add = models.GenericIPAddressField()
    elevator_id = models.IntegerField()
    floor_id = models.IntegerField()

    class Meta:
        unique_together = (('ip_add', 'elevator_id'),)
