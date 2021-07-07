# Copyright (C) 2018 The MindbreakersServer Contributors.
#
# This file is part of MindbreakersServer.
#
# MindbreakersServer is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any later version.
#
# MindbreakersServer is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE.  See the GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License along with Hunter2.  If not, see <http://www.gnu.org/licenses/>.

"""server URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.8/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Add an import:  from blog import urls as blog_urls
    2. Add a URL to urlpatterns:  url(r'^blog/', include(blog_urls))
"""
from django.conf.urls import include, url
from django.urls import path
from django.contrib.auth import views as base_auth_views
from django.views.generic.base import RedirectView
from django.contrib.flatpages import views as flatpage_views
from . import views

urlpatterns = [
    # Auth and Accounts
    url(r'^signup/$', views.auth.SignUp.as_view(), name='signup'),
    url(r'^login/$', views.auth.account_login, name='login'),
    url(r'^logout/$', views.auth.account_logout, name='logout'),
    url(r'^registration/$', views.auth.Registration.as_view(), name='registration'),
    url(r'^manage-team/$', views.auth.ManageTeam.as_view(), name='manage-team'),
    url(r'^profile/$', views.auth.profile, name='profile'),    
    #bot
    url('teaminfo/(?P<team_token>[0-9a-f-]+)', views.auth.TeamInfoView.as_view(), name='team_info'),

]
