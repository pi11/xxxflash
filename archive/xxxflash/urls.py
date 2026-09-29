# -*- coding: utf-8 -*-
from django.contrib import admin
from django.conf import settings
from django.conf.urls import include, url

admin.autodiscover()

urlpatterns = [
    url(r'', include('flash.urls')),
    url(r'^secret-admin-lol/', include(admin.site.urls)),
                       
]

