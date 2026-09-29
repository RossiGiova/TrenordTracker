"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import include, path

import os

urlpatterns = [
    path("", include("trains.urls")),
]

# L'area /admin/ e' attiva solo in sviluppo o con DJANGO_ADMIN=1 (in produzione resta chiusa)
from django.conf import settings as _s
if _s.DEBUG or os.environ.get("DJANGO_ADMIN") == "1":
    urlpatterns.insert(0, path("admin/", admin.site.urls))
