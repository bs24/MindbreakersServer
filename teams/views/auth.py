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

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout, login, views
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, reverse
from django.db.models.functions import Lower
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.http import Http404, JsonResponse
from django.core.exceptions import ValidationError

import random
import re

from hunts.models import Hunt
from teams.models import Person, Team
from teams.forms import UserForm, PersonForm
from teams.utils import parse_attributes
from hunts.views.mixin import APITokenRequiredMixin

import logging
logger = logging.getLogger(__name__)




def account_login(request):
    """ A mostly static view to render the login selection. Next url parameter is preserved. """

    if 'next' in request.GET:
        context = {'next': request.GET['next']}
    else:
        context = {'next': "/"}

    return views.LoginView.as_view(template_name="auth/login.html")(request)


class SignUp(View):
    def get(self, request):
        """
        A view to create user and person objects from valid user POST data, as well as render
        the account creation form.
        """

        uf = UserForm(prefix='user')
        return render(request, "auth/signup.html", {'uf': uf})

    def post(self, request):
        uf = UserForm(request.POST, prefix='user')
        if uf.is_valid():
            user = uf.save()
            user.set_password(user.password)
            user.backend = 'django.contrib.auth.backends.ModelBackend'
            user.save()
            person = Person()
            person.user = user
            person.save()
            login(request, user)
            logger.info("User created: %s" % (str(person)))
            return redirect(reverse('current_hunt'))
        else:
            return render(request, "auth/signup.html", {'uf': uf})



def account_logout(request):
    """ A view to logout the user. """

    logout(request)
    messages.success(request, "Logout successful")
    if 'next' in request.GET:
        additional_url = request.GET['next']
    else:
        additional_url = ""
    return redirect(reverse('index'))



class Registration(LoginRequiredMixin, View):
    login_url = '/login/'

    """
    The view that handles team registration. Mostly deals with creating the team object from the
    post request. The rendered page is nearly entirely static.
    """
    def get(self, request):
        curr_hunt = Hunt.objects.get(is_current_hunt=True)
        team = curr_hunt.team_from_user(request.user)

        if(curr_hunt.is_locked):
            return redirect(reverse("index"))
        if(team is not None):
            return redirect(reverse('manage-team'))
        else:
            teams = curr_hunt.team_set.order_by(Lower('team_name'))
            return render(request, "auth/registration.html",
                          {'teams': teams, 'curr_hunt': curr_hunt})

    def post(self, request):
        curr_hunt = Hunt.objects.get(is_current_hunt=True)
        
        if(request.POST["form_type"] == "create_team"):
            if(request.user.person.teams.filter(hunt=curr_hunt).count()>0):
                messages.error(request, "You already have a team for this hunt")
            elif len(request.POST.get("team_name")) > 100:
                messages.error(request, "Your team name is too long")
            elif(not re.fullmatch("[A-Za-z0-9][A-Za-z0-9 ]*", request.POST.get("team_name"))):
                messages.error(request, "Your team name must contain only alphanumeric characters and spaces and not start by a space.")
            else:
                team_name_upper =  request.POST.get("team_name").replace(" ","").upper()
                conflict = False
                for name in curr_hunt.team_set.values_list('team_name', flat=True):
                  if name.replace(" ","").upper() == team_name_upper:
                    conflict = True
                    break
                if conflict: #(curr_hunt.team_set.filter(team_name__iexact=request.POST.get("team_name")).exists()):
                  messages.error(request, "The team name you have provided already exists.")
                else:
                    join_code = ''.join(random.choice("ACDEFGHJKMNPRSTUVWXYZ2345679") for _ in range(5))
                    team = Team.objects.create(team_name=request.POST.get("team_name"), hunt=curr_hunt, join_code=join_code)
                    request.user.person.teams.add(team)
                    logger.info("User %s created team %s" % (str(request.user), str(team)))
                    return redirect(reverse('manage-team'))

        elif(request.POST["form_type"] == "join_team"):
            team = curr_hunt.team_set.get(team_name=request.POST.get("team_name"))
            if(len(team.person_set.all()) >= team.hunt.team_size):
                messages.error(request, "The team you have tried to join is already full.")
                team = None
            elif(team.join_code.lower() != request.POST.get("join_code").lower()):
                messages.error(request, "The team join code you have entered is incorrect.")
                team = None
            else:
                request.user.person.teams.add(team)
                logger.info("User %s joined team %s" % (str(request.user), str(team)))
                return redirect(reverse('manage-team'))

        teams = curr_hunt.team_set.order_by(Lower('team_name'))
        return render(request, "auth/registration.html",
                      {'teams': teams, 'curr_hunt': curr_hunt})


class ManageTeam(View):
    """
    The view that handles team registration. Mostly deals with creating the team object from the
    post request. The rendered page is nearly entirely static.
    """

    def get(self, request):
        curr_hunt = Hunt.objects.get(is_current_hunt=True)
        team = curr_hunt.team_from_user(request.user)

        if(team is not None):
            context = {'registered_team': team, 'curr_hunt': curr_hunt}
            context['token'] = team.token
            context['discord_url'] = curr_hunt.discord_url
            context['discord_bot_id'] = curr_hunt.discord_bot_id

            return render(request, "auth/manage-team.html",
                          context)
        else:
            return redirect(reverse('registration'))


    def post(self, request):
        curr_hunt = Hunt.objects.get(is_current_hunt=True)
        team = curr_hunt.team_from_user(request.user)

        if("form_type" in request.POST):
            if(request.POST["form_type"] == "leave_team"):
                
                if (team.puz_solved.count()>0):
                  messages.error(request, "You cannot leave a team that has started the hunt.")
                else:
                  request.user.person.teams.remove(team)
                  logger.info("User %s left team %s" % (str(request.user), str(team)))
                  if(team.person_set.count() == 0 and team.puz_solved.count()==0):
                      logger.info("Team %s was deleted because it was empty." % (str(team)))
                      team.delete()
                  team = None
                  return redirect(reverse('registration'))
                
                  messages.success(request, "You have successfully left the team.")
            elif(request.POST["form_type"] == "new_location" and team is not None):
                old_location = team.location
                team.location = request.POST.get("team_location")
                team.save()
                logger.info("User %s changed the location for team %s from %s to %s" %
                            (str(request.user), str(team.team_name), old_location, team.location))
                messages.success(request, "Location successfully updated")
            elif(request.POST["form_type"] == "new_name" and team is not None and
                    not team.hunt.in_reg_lockdown):
                if(team.discord_linked):
                    messages.error(request, "You cannot change your team name after joining Discord. Please contact the admins.")
                elif len(request.POST.get("team_name")) > 100:
                    messages.error(request, "Your team name is too long")
                elif(not re.fullmatch("[A-Za-z0-9][A-Za-z0-9 ]*", request.POST.get("team_name"))):
                    messages.error(request, "Your team name must contain only alphanumeric characters and spaces and not start by a space.")
                else:
                    team_name_upper =  request.POST.get("team_name").replace(" ","").upper()
                    conflict = False
                    for name in curr_hunt.team_set.values_list('team_name', flat=True):
                      if name.replace(" ","").upper() == team_name_upper:
                        conflict = True
                        break
                    if conflict: #(curr_hunt.team_set.filter(team_name__iexact=request.POST.get("team_name")).exists()):
                        messages.error(request, "The team name you have provided already exists.")
                    else:
                        old_name = team.team_name
                        team.team_name = request.POST.get("team_name")
                        team.save()
                        logger.info("User %s renamed team %s to %s" %
                                    (str(request.user), old_name, team.team_name))
                        messages.success(request, "Team name successfully updated")

        return render(request, "auth/manage-team.html",
                      {'registered_team': team, 'curr_hunt': curr_hunt})



@login_required
def profile(request):
    """ A view to handle user information update POST data and render the user information form. """

    if request.method == 'POST':
        uf = UserForm(request.POST, instance=request.user)
        pf = PersonForm(request.POST, instance=request.user.person)
        if uf.is_valid() and pf.is_valid():
            user = uf.save()
            user.set_password(user.password)
            user.save()
            pf.save()
            login(request, user)
            messages.success(request, "User information successfully updated.")
        else:
            context = {'user_form': uf, 'person_form': pf}
            return render(request, "auth/user_profile.html", context)
    user_form = UserForm(instance=request.user)
    person_form = PersonForm(instance=request.user.person)
    context = {'user_form': user_form, 'person_form': person_form}
    return render(request, "auth/user_profile.html", context)
    

# interface for the discord bot
class TeamInfoView(APITokenRequiredMixin, View):
    def get(self, request, team_token):
        try:
            team = Team.objects.get(token=team_token)
        except ValidationError:
            return JsonResponse({
                'result': 'Not Found',
                'message': 'Invalid team token',
            }, status=404)
        except Team.DoesNotExist:
            return JsonResponse({
                'result': 'Not Found',
                'message': 'Several teams share this token',
            }, status=404)
        team.discord_linked = True
        team.save()
        return JsonResponse({
            'result': 'OK',
            'team': {
                'name': team.team_name,
                'nb_ep_solve': team.ep_solved.count()
            },
        })

    
