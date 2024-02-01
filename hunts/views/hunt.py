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

from string import Template
from datetime import datetime
from dateutil import tz
from django.conf import settings
from datetime import timedelta
from ratelimit.utils import is_ratelimited
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, Http404, HttpResponseForbidden, HttpResponseNotFound
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.template import RequestContext
from django.template.loader import render_to_string
from django.utils import timezone
from django.views import View
from django.utils.encoding import smart_str
from django.db.models import F
from django.urls import reverse_lazy, reverse
from pathlib import Path
from django.db.models import F, Max, Count, Min, Subquery, OuterRef
from django.db.models.fields import PositiveIntegerField
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.mixins import LoginRequiredMixin
import mimetypes
import json
import os
import re

from hunts.models import Puzzle, Hunt, Guess, Unlockable
from teams.models import PuzzleSolve, EpisodeSolve, TeamEpisodeLink
from .mixin import RequiredPuzzleAccessMixin, RequiredSolutionAccessMixin
from hashlib import sha256

import logging
logger = logging.getLogger(__name__)

DT_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def format_duration(arg):
    try:
      seconds = int(arg.total_seconds())
      if seconds < 60:
        return str(seconds) + "s"
      elif seconds < 3600:
        return str(int(seconds/60)) + "m" + str(seconds % 60) + "s"
      elif seconds < 3600*24:
        return str(int(seconds/3600)) + "h" + str(int((seconds % 3600)/60)) + "m"
      else:
        return str(int(seconds/3600/24)) + "d" + str(int((seconds % (3600*24))/3600)) + "h"
#      return str(timedelta(seconds=int(arg.total_seconds())))
    except AttributeError:
      return ''


class PuzzleFile(RequiredPuzzleAccessMixin, View):
    def get(self, request, puzzle_id, file_path):
        puzzle = request.puzzle
        puzzle_file = get_object_or_404(puzzle.puzzlefile_set, url_path=file_path)

        pathname = smart_str(os.path.join(settings.MEDIA_ROOT, puzzle_file.file.path))
        try:
           with open(pathname, "rb") as f:
              return HttpResponse(f.read(), content_type=mimetypes.guess_type(pathname)[0])
        except IOError:
           raise Http404('Puzzle file not found')




class SolutionFile(RequiredSolutionAccessMixin, View):
    def get(self, request, puzzle_id, file_path):
        puzzle = request.puzzle
        puzzle_file = get_object_or_404(puzzle.solutionfile_set, url_path=file_path)

        pathname = smart_str(os.path.join(settings.MEDIA_ROOT, puzzle_file.file.path))
        try:
#            return sendfile(request, puzzle_file.file.path)
           with open(pathname, "rb") as f:
               return HttpResponse(f.read(), content_type="application/pdf")
        except IOError:
           raise Http404('Solution file not found')





def current_hunt(request):
    """ A simple view that calls ``teams.hunt_views.hunt`` with the current hunt's number. """
    return redirect(reverse('hunt', kwargs={'hunt_num' : Hunt.objects.get(is_current_hunt=True).hunt_number}))


class HuntIndex(View):
    def get(self, request, hunt_num):
        """
        The main view to render hunt templates. Does various permission checks to determine the set
        of puzzles to display and then renders the string in the hunt's "template" field to HTML.
        """
        user = request.user
        hunt = request.hunt # Populated by middleware
        team = request.team # Populated by middleware

        # Admins get all access, wrong teams/early lookers get an error page
        # real teams get appropriate puzzles, and puzzles from past hunts are public
        if not hunt.can_access(user, team):
            if(hunt.is_locked):
                return redirect(reverse("index"))
            if(hunt.is_open):
                return redirect(reverse('registration'))

        episodes = request.hunt.get_formatted_episodes(request.user, request.team)
        text = hunt.template
        # if template is empty, redirect to first unsolved puzzle
        if text == '':
            # TODO find first unsolved puzzle
            return redirect(reverse('puzzle', kwargs={'puzzle_id': episodes[0]['puz'][0].puzzle_id} ))


        message = ''
        time_zone = tz.gettz(settings.TIME_ZONE)


        if team is not None:
            if user.is_staff:
              message = "You're an admin, you should delete your progress before the hunt starts<br>"
            if team.is_playtester_team:
              message = "Thanks for beta-testing the hunt, please stay focused ;)<br>"
            ep_solved = team.ep_solved.count()
            if len(episodes)>0 and ep_solved == len(episodes):
              if len(episodes) == hunt.episode_set.count():
                try:
                  time = team.episodesolve_set.get(episode = episodes[-1]['ep']).time
                except:
                  return HttpResponseNotFound('<h1>Inconsistent database stucture</h1>')
                message = message + 'Congratulations! <br>You have finished the hunt at rank ' + str(EpisodeSolve.objects.filter(episode= episodes[-1]['ep'], time__lte= time).count())
              else:
                try:
                  ep_unlock = TeamEpisodeLink.objects.get(episode=episodes[-1]['ep'].unlocks, team=team)
                  ep_solve = EpisodeSolve.objects.get(episode=episodes[-1]['ep'], team=team)
                  rank = str(EpisodeSolve.objects.filter(episode= episodes[-1]['ep'], time__lte= ep_solve.time).count())
                  message = message + 'Congratulations on finishing Episode ' + str(len(episodes)) + ' at rank ' + rank + '! <br> Next Episode will start at ' + (ep_unlock.episode.start_date - ep_unlock.headstart).astimezone(time_zone).strftime('%H:%M, %d/%m %Z')
                except:
                  return HttpResponseNotFound('<h1>Last Episode finished without unlocking the next one</h1>')
            if ep_solved>0:
              message = message + ' <br>  -------------  <br> Use "!finish ' + str(team.token) +'" on your private team channel on discord to unlock the finisher channel'
            if len(episodes) == 0:
              unlocks = team.ep_unlocked
              if (unlocks.count()>0):
                  message = message + 'Welcome to the hunt! <br> The first Episode will start at ' + unlocks.first().start_date.astimezone(time_zone).strftime('%H:%M, %d/%m %Z')
                

        context = {'hunt': hunt, 'episodes': episodes, 'team': team, 'text': text, 'message': message}
        return render(request, 'hunt/hunt.html', context)



def get_ratelimit_key(group, request):
    return request.ratelimit_key



# simple way to encode a prepuzzle response string
def encode(key, string):
    encoded_chars = []
    for i in range(len(string)):
        key_c = key[i % len(key)]
        encoded_c = chr(ord(string[i]) + ord(key_c) % 256)
        encoded_chars.append(encoded_c)
    return "".join(encoded_chars)

@method_decorator(csrf_exempt, name='dispatch')
class PuzzleView(RequiredPuzzleAccessMixin, View):
    """
    A view to handle answer guesss via POST, handle response update requests via AJAX, and
    render the basic per-puzzle pages.
    """

    def check_rate(self,request, puzzle_id):
        request.puzzle = get_object_or_404(Puzzle, puzzle_id__iexact=puzzle_id)
        request.hunt = request.puzzle.episode.hunt
        request.team = request.hunt.team_from_user(request.user)

        limited = False
        if(request.team is not None):
            request.ratelimit_key = request.user.username
            limited = is_ratelimited(request, fn=PuzzleView.as_view(), key='user', rate='1/7s', method='POST',
                           increment=True)
        #if (not limited and not request.hunt.is_public):
        #    limited = is_ratelimited(request, fn=PuzzleView.as_view(), key=get_ratelimit_key, rate='5/m', method='POST',
        #                   increment=True)

        return limited or getattr(request, 'limited', False)

    def get(self, request, puzzle_id):
        if self.check_rate(request, puzzle_id):
            logger.info("User %s rate-limited for puzzle %s" % (str(request.user), puzzle_id))
            return HttpResponseForbidden()

        puzzle_files = {f.slug: reverse(
            'puzzle_file',
            kwargs={
                'puzzle_id': puzzle_id,
                'file_path': f.url_path,
            }) for f in request.puzzle.puzzlefile_set.filter(slug__isnull=False)
        }
        text = Template(request.puzzle.template).safe_substitute(**puzzle_files)
        episodes = request.hunt.get_formatted_episodes(request.user, request.team)

        try:
          puzzle_solve = PuzzleSolve.objects.get(puzzle__puzzle_id=puzzle_id, team=request.team)
          status = 'solved'
        except PuzzleSolve.DoesNotExist:
          status = 'unsolved'


        context = {
            'hunt': request.hunt,
            'episodes': episodes,
            'puzzle': request.puzzle,
            'eureka': request.puzzle.eureka_set.filter(admin_only=False).count()>0,
            'team': request.team,
            'text':text,
            'status': status
        }

        if not request.hunt.is_demo and not request.hunt.is_finished:
            return render(request, 'puzzle/puzzle.html', context)
        elif request.hunt.is_demo:
            # Prepuzzle
            context['prepuzzle_values'] = {'answerHash': sha256(("SuperRandomInitialSalt" + request.puzzle.answer.replace(" ", "").lower()).encode('utf-8')).hexdigest(), 
                                          'eurekaHashes': [sha256(("SuperRandomInitialSalt" + eur.replace(" ", "").lower()).encode('utf-8')).hexdigest() for eur in request.puzzle.eureka_set.filter(admin_only=False).values_list('answer', flat=True)],
                                          'responseEncoded': encode(request.puzzle.answer.replace(" ", "").lower(), request.puzzle.demo_response),
                                          }
            return render(request, 'puzzle/prepuzzle.html', context)
        else:
            # Postpuzzle
            
            
            context['solutions'] = [ reverse(
                'solution_file',
                kwargs={
                    'puzzle_id': puzzle_id,
                    'file_path': f.url_path,
                }) for f in request.puzzle.solutionfile_set.all()
            ]
            
            
            
            context['postpuzzle_values'] = {'answer': encode( "secretkey", request.puzzle.answer), 
                                            'answer_regex': encode("secretkey", request.puzzle.answer_regex), 
                                            'hints': [{'text': hi.text, 'time':hi.time} for hi in request.puzzle.hint_set.order_by('time')],
                                            'eurekas': [{'regex': encode("secretkey", eur.regex), 'answer':encode("secretkey", eur.answer), 'feedback': encode("secretkey", eur.feedback)} for eur in request.puzzle.eureka_set.filter(admin_only=False).all()],
                                          }
            if request.team is not None:
              context['guesses'] = Guess.objects.filter(puzzle=request.puzzle, team=request.team).order_by('-guess_time').annotate(name=F('user__username' ))
            return render(request, 'puzzle/postpuzzle.html', context)



    def post(self, request, puzzle_id):
        if self.check_rate(request, puzzle_id):
            logger.info("User %s rate-limited for puzzle %s" % (str(request.user), puzzle_id))
            return JsonResponse({'error': 'too fast'}, status=429)

        team = request.team
        puzzle = request.puzzle
        user = request.user
        
        # Dealing with answer guesss, proper procedure is to create a guess
        # object and then rely on Guess.respond for automatic responses.
        if(team is None or puzzle.episode.hunt.is_finished or team.hunt != puzzle.episode.hunt):
                # If the hunt isn't public and you aren't signed in, please stop...
                return JsonResponse({'error':'fail'})


        given_answer = request.POST.get('answer', '')
        if given_answer == '':
            return JsonResponse({'error': 'no answer given'}, status=400)
        if not given_answer.replace(" ","").replace("=","").isalnum():
            return JsonResponse({'error': 'do not disable client-side sanitization...'}, status=400)

        guess = Guess(
            guess_text=given_answer,
            team=team,
            user=user,
            puzzle=puzzle,
            guess_time=timezone.now()
        )
        guess.save()
        response = guess.respond()
        if not guess.is_correct:
            now = timezone.now()
            minimum_time = timedelta(seconds=5)

            response['guess'] = given_answer
            response['timeout_length'] = minimum_time.total_seconds() * 1000
            response['timeout_end'] = str(now + minimum_time)
        response['by'] = request.user.username
        
        return JsonResponse(response)


@login_required
def unlockables(request):
    """ A view to render the unlockables page for hunt participants. """
    team = Hunt.objects.get(is_current_hunt=True).team_from_user(request.user)
    if(team is None):
        return render(request, 'access_error.html', {'reason': "team"})
    unlockables = Unlockable.objects.filter(puzzle__in=team.puz_solved.all())
    return render(request, 'hunt/unlockables.html', {'unlockables': unlockables, 'team': team})



def int_to_rank(n):
  return "%d%s" % (n,"tsnrhtdd"[(n//10%10!=1)*(n%10<4)*n%10::4])
#TODO: clean time format + clear useless info out of all_teams before sending
@login_required
def leaderboard(request):
    curr_hunt = get_object_or_404(Hunt, is_current_hunt=True)
    teams = curr_hunt.team_set.all()
    all_teams = teams.annotate(solves=Count('puz_solved')).filter(solves__gt=0)
    all_teams = all_teams.annotate(last_time=Max('puzzlesolve__guess__guess_time'))
    all_teams = all_teams.order_by(F('solves').desc(nulls_last=True),
                                   F('last_time').asc(nulls_last=True))
    
    if all_teams.count() > 10 and all_teams[9].ep_solved.count() == curr_hunt.episode_set.count():
      all_teams = all_teams.filter(solves=all_teams[0].solves)
    else:
      all_teams = all_teams[:10]

    team = Hunt.objects.get(is_current_hunt=True).team_from_user(request.user)
    if(team is None):
      solves_data = []
    else:
      solves = team.puzzlesolve_set.annotate(time=F('guess__guess_time'), puzId = F('puzzle__puzzle_id')).order_by('time')
      unlocks = team.teampuzzlelink_set.annotate(puzId = F('puzzle__puzzle_id'), name = F('puzzle__puzzle_name')).order_by('time')

      solves_data = []
      for unlock in unlocks.all():
        try:
          solve = solves.get(puzId=unlock.puzId)
          rank = int_to_rank(PuzzleSolve.objects.filter(puzzle= unlock.puzzle, guess__guess_time__lt= solve.time).count()+1)
          solves_data.append({'name' : unlock.name, 'sol_time': solve.time, 'duration':  format_duration(solve.duration), 'rank': rank})
        except ObjectDoesNotExist:
          start = unlock.puzzle.starting_time_for_team(unlock.team)
          if (timezone.now() > start):
            solves_data.append({'name' : unlock.name, 'sol_time': '' , 'duration':  format_duration(timezone.now()-start)})

    context = {'team_data': all_teams, 'solve_data': solves_data}
    return render(request, 'hunt/leaderboard.html', context)
