"""notifhandler URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.11/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""

from django.conf.urls import url
from django.contrib import admin
from django.contrib.auth import views as auth_views

from notifier import views as notif_views

admin.site.site_header = 'Notifhandler Admin'
admin.site.site_title = 'Notifhandler Admin'
admin.site.index_title = 'Notifhandler Admin'

urlpatterns = [
    url(r'^$', notif_views.view),
    url(r'^admin/', admin.site.urls),

    url(r'^accounts/login/$', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    url(r'^logout/$', auth_views.LogoutView.as_view(template_name='logged_out.html'), name='logout'),

    url(r'^paste$', notif_views.paste),
    url(r'^paste1$', notif_views.paste1),
    url(r'^paste_error$', notif_views.paste_error),

    url(r'^paste_verte$', notif_views.paste_verte),
    url(r'^paste_sodimac$', notif_views.paste_sodimac),

    url(r'^pasteauth$', notif_views.paste_with_auth),
    url(r'^notifauth$', notif_views.notifauth),
    url(r'^sorter/api/execute_command$', notif_views.sorter),

    url(r'^view$', notif_views.view),
    url(r'^view_by_ip$', notif_views.view_by_ip),
    url(r'^notifications/verte/', notif_views.notif_verte),
    url(r'^notifications/sodimac/', notif_views.notif_sodimac),

    url(r'^get_by_exid$', notif_views.get_by_exid),
    url(r'^view_inventory$', notif_views.view_inventory),

    url(r'^create_url$', notif_views.create_url),
    url(r'^view_url$', notif_views.view_url),
    url(r'^delete_url$', notif_views.delete_url),

    url(r'^agent_status$', notif_views.agent_status),
    url(r'^agent_event', notif_views.agent_event),
    url(r'^agent_event_big', notif_views.agent_event),

]
