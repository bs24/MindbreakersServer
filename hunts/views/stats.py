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

from datetime import datetime
from dateutil import tz
from datetime import timedelta
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import admin
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import EmailMessage
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse, HttpResponseNotFound, HttpResponseRedirect
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.contrib import messages
from django.db.models import F, Max, Count, Min, Subquery, OuterRef, Value, ExpressionWrapper, fields, Avg, Sum
from django.db.models.fields import PositiveIntegerField
from django.db.models.functions import Lower
from huey.contrib.djhuey import result
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.dateparse import parse_datetime
import json
from copy import deepcopy
from collections import Counter
# from silk.profiling.profiler import silk_profile

import re
import math
import os.path
from hunts.models import Guess, Hunt, Puzzle
from teams.models import Team, TeamPuzzleLink, PuzzleSolve, Person
from teams.forms import GuessForm, UnlockForm, EmailForm, LookupForm

DT_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'

UPDATE_STATS = False


def add_apps_to_context(context, request):
    context['available_apps'] = admin.site.get_app_list(request)
    return context

def get_last_hunt_or_none(request):
    if (request.user.is_staff):
        hunt = Hunt.objects.filter(is_current_hunt=True)
        nb_puzzle = len([0 for episode in hunt.first().episode_set.all() for puzzle in episode.puzzle_set.all()])
        return hunt.annotate(puz=Value(nb_puzzle, output_field=PositiveIntegerField())).first()

    last_hunts = Hunt.objects.filter(end_date__lt=timezone.now()).order_by('-end_date')
    if last_hunts.count() == 0:
      return None
    nb_puzzle = len([0 for episode in last_hunts.first().episode_set.all() for puzzle in episode.puzzle_set.all()])

    hunt = last_hunts[:1].annotate(puz=Value(nb_puzzle, output_field=PositiveIntegerField())).first()
    return hunt

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

def int_to_rank(n):
  return "%d%s" % (n,"tsnrhtdd"[(n//10%10!=1)*(n%10<4)*n%10::4])



@login_required
def stats(request):
    ''' General stats of the hunt: #teams, #guesses, #puzzles solved, total time spent on the hunt... '''
    hunt = get_last_hunt_or_none(request)
    if hunt == None:
      context = {'hunt': None}
      return render(request, 'stats/stats.html', context)

    teams = hunt.team_set.count()
    people = hunt.team_set.annotate(team_size=Count('person')).aggregate(res=Sum('team_size'))['res']
    guesses = Guess.objects.filter(puzzle__episode__hunt=hunt).count()
    solved = PuzzleSolve.objects.filter(puzzle__episode__hunt=hunt).count()


    context = {'hunt': hunt, 'teams': teams, 'guesses': guesses, 'solved': solved, 'people':people}
    return render(request, 'stats/stats.html', context)


@login_required
def teams(request):
    ''' General view of all teams:  rank, number of solved puzzles, finish time (if finished) '''
    hunt = get_last_hunt_or_none(request)
    if hunt == None:
      context = {'hunt': None}
      return render(request, 'stats/teams.html', context)



    
    # load json if exists & non staff
    template_filename =  'stats/static/teams.json'
    filename =  'hunts/templates/' + template_filename

    if ((not request.user.is_staff or not UPDATE_STATS) and os.path.exists(filename)):
      with open(filename) as json_file:
        context = json.load(json_file)
        for d in context['team_data']:
          d.update({'last_time': parse_datetime(d['last_time']) if d['last_time'] is not None else None})
          
    else:
      teams = hunt.team_set
      teams = teams.annotate(solves=Count('puz_solved'))
      teams = teams.order_by(F('solves').desc(nulls_last=True),
                                     F('last_time').asc(nulls_last=True))
      teams = teams.annotate(last_time=Max('puzzlesolve__guess__guess_time'))
      
      team_data = []   
      for team in teams.all():
        hints = 0
        for solve in team.puzzlesolve_set.all():
            duration = solve.duration
            hints += sum([hint.delay_for_team(team) < duration for hint in solve.puzzle.hint_set.all()])
        guesses = Guess.objects.filter(puzzle__episode__hunt=hunt, team__team_name=team.team_name).count()
        team_data.append({'team_name': team.team_name, 'solves': team.solves, 'last_time':team.last_time, 'guesses':guesses, 'hints':hints, 'pk':team.pk, 'size': team.size})

      context = {'team_data': team_data, 'hunt': {'hunt_name':hunt.hunt_name, 'display_start_date': hunt.display_start_date, 'puz' : hunt.puz}}
      
      
      # write json
      with open(filename, 'w') as outfile:
        json.dump(context, outfile, cls=DjangoJSONEncoder)
      
    return render(request, 'stats/teams.html', context)

@login_required
def team(request):
    ''' Summary of a single team performance, asked by /?team=ID: time / duration per puzzle, rank on each, number of guesses, number of hints needed
      global param: #teammates'''
      
      
      
    hunt = get_last_hunt_or_none(request)
    context = {'hunt': None}
    if hunt == None:
      return render(request, 'stats/team.html', context)
      
    try:
      team = Team.objects.get(pk=request.GET.get("team"))
    except ObjectDoesNotExist:
      return render(request, 'stats/team.html', context)

    if team.hunt != hunt:
      return render(request, 'stats/team.html', context)

    if(team is None):
      return render(request, 'stats/team.html', context)

    
    # load json if exists & non staff
    template_filename =  'stats/static/team-' + str(request.GET.get("team")) + '.json'
    filename =  'hunts/templates/' + template_filename

    if ((not request.user.is_staff or not UPDATE_STATS) and os.path.exists(filename)):
      with open(filename) as json_file:
        context = json.load(json_file)
        for d in context['solve_data']:
          d.update({'sol_time': parse_datetime(d['sol_time'])})
        
    else:
      solves = team.puzzlesolve_set.annotate(time=F('guess__guess_time'), puzId = F('puzzle__puzzle_id')).order_by('time')
      unlocks = team.teampuzzlelink_set.annotate(puzId = F('puzzle__puzzle_id'), name = F('puzzle__puzzle_name')).order_by('time')

      solves_data = []
      for unlock in unlocks.all():
        duration = ''
        solvetime = ''
        rank = ''
        rankduration = ''
        hints= ''
        nbguesses = team.guess_set.filter(puzzle=unlock.puzzle).count()
        try:
          solve = solves.get(puzId=unlock.puzId)
          solvetime = solve.time
          duration = solve.duration
          rank = int_to_rank(PuzzleSolve.objects.filter(puzzle= unlock.puzzle, guess__guess_time__lt= solvetime).count()+1)
     #     wrap = ExpressionWrapper(F('guess__guess_time')-F('unlock_time'), output_field=fields.DurationField())
          rankduration = int_to_rank(PuzzleSolve.objects.filter(puzzle = unlock.puzzle, duration__lt=duration).count()+1)
          hints = sum([hint.delay_for_team(team) < duration for hint in unlock.puzzle.hint_set.all()])
          duration = format_duration(duration)
        except ObjectDoesNotExist:
          pass

        solves_data.append({'name' : unlock.name, 'pk':unlock.puzzle.pk, 'sol_time': solvetime , 'duration' : duration, 'rank' : rank, 'rankduration': rankduration, 'hints': hints, 'nbguesses': nbguesses})

      context = {'solve_data': solves_data, 'team': {'team_name': team.team_name, 'size': team.size}, 'hunt': {'hunt_name':hunt.hunt_name, 'display_start_date': hunt.display_start_date}}
      
      # write json
      with open(filename, 'w') as outfile:
        json.dump(context, outfile, cls=DjangoJSONEncoder)
    
    
    return render(request, 'stats/team.html', context)


@login_required
def puzzles(request):
    ''' Summary of all puzzles: #teams successful, fastest time / duration / smallest number of hints, average duration / number of hints, link to solution file '''
    hunt = get_last_hunt_or_none(request)
    if hunt == None:
      context = {'hunt': None}
      return render(request, 'stats/puzzles.html', context)

    
    # load json if exists & non staff
    template_filename =  'stats/static/puzzles.json'
    filename =  'hunts/templates/' + template_filename

    if ((not request.user.is_staff or not UPDATE_STATS) and os.path.exists(filename)):
      with open(filename) as json_file:
        context = json.load(json_file)
        for d in context['data']:
          d.update({'min_time': parse_datetime(d['min_time'])})
          d.update({'av_time': parse_datetime(d['av_time'])})
          
    else:
      puzzle_list = [puzzle for episode in hunt.episode_set.order_by('ep_number').all() for puzzle in episode.puzzle_set.all()]

      data = []
      reftime = timezone.now()
      for puz in puzzle_list:
        solves = PuzzleSolve.objects.filter(puzzle=puz)
        unlocks = TeamPuzzleLink.objects.filter(puzzle=puz)
        dic = solves.annotate(ref=F('guess__guess_time')-reftime).aggregate(min_time = Min('ref')+reftime, av_dur= Avg('duration'), min_dur = Min('duration'), av_time=Avg('ref')+reftime)
        dic['av_dur'] = format_duration(dic['av_dur'])
        dic['min_dur'] = format_duration(dic['min_dur'])
        dic['success'] = solves.count()
        dic['name'] = puz.puzzle_name
        hints = [sum([hint.delay_for_team(sol.team) < sol.duration for hint in puz.hint_set.all()]) for sol in solves]
        dic['min_hints'] = 0 if len(hints)==0 else min(hints)
        dic['av_hints'] =  0 if len(hints)==0 else round(sum(hints)/len(hints), 2)
        if (unlocks.count() == 0):
          dic['guesses'] = 0
        else:
          dic['guesses'] = round(Guess.objects.filter(puzzle=puz).count() / unlocks.count(), 2)
        dic['pk'] = puz.pk
        data.append(dic)
        
      context = {'hunt': {'hunt_name':hunt.hunt_name, 'display_start_date': hunt.display_start_date}, 'data': data}
      
      # write json
      with open(filename, 'w') as outfile:
        json.dump(context, outfile, cls=DjangoJSONEncoder)
    
    return render(request, 'stats/puzzles.html', context)



@login_required
def puzzle(request):
    ''' Summary of 1 puzzle results: each team duration, time solved, guesses, number of hints seen, duration to get each eureka. Also show all eurekas / hints '''
    hunt = get_last_hunt_or_none(request)
    context = {'name': "No hunt found"}
    if hunt == None:
      return render(request, 'stats/puzzle.html', context)

    context = {'name': "No puzzle found"}
    try:
      puz = Puzzle.objects.get(pk=request.GET.get("puzzle"))
    except ObjectDoesNotExist:
      return render(request, 'stats/puzzle.html', context)


    context = {'name': "Puzzle from wrong hunt"}
    if puz.episode.hunt != hunt:
      return render(request, 'stats/puzzle.html', context)


    
    
    # load json if exists & non staff
    template_filename =  'stats/static/puzzle-' + str(request.GET.get("puzzle")) + '.json'
    filename =  'hunts/templates/' + template_filename

    if ((not request.user.is_staff or not UPDATE_STATS) and os.path.exists(filename)):
      with open(filename) as json_file:
        context = json.load(json_file)
        for d in context['data']:
          d.update({'sol_time': parse_datetime(d['sol_time'])})

    else:
    
      solves = PuzzleSolve.objects.filter(puzzle=puz)

      data = []

      for sol in solves:
        duration = sol.duration
        sol_time = sol.guess.guess_time
        guesses = sol.team.guess_set.filter(puzzle=puz, guess_time__lte=sol_time).count()
        hints = sum([hint.delay_for_team(sol.team) < sol.duration for hint in puz.hint_set.all()])
        eurekas = [ {'txt' : eur.eureka.answer , 'time': format_duration(eur.time - sol_time + duration) } for eur in sol.team.teameurekalink_set.filter(eureka__puzzle=puz,time__lt=sol_time).all()]
        data.append({'duration':format_duration(duration), 'sol_time': sol_time, 'guesses':guesses, 'hints': hints, 'eurekas':eurekas, 'team':sol.team.team_name, 'team_pk':sol.team.pk})
        
        
      guesses = Guess.objects.filter(puzzle=puz).annotate(teampk=F('team'))
      
      guesses = list(dict.fromkeys([(g.guess_text.lower().replace(" ", ""), g.teampk) for g in guesses.all()])) # remove duplicate guesses per team
      guesses = Counter(elem[0] for elem in guesses).most_common(30) # want 10 most common uncorrect answers, take some margin to remove eureka and answers
      
      common_guess = []
      
      for g,c in guesses:
        if c < 2:
          break
        if (g == puz.answer.lower().replace(" ","") or
                 (puz.answer_regex!="" and re.fullmatch(puz.answer_regex, g, re.IGNORECASE))):
          continue
          
        eur = False
        for resp in puz.eureka_set.all():
          if(re.fullmatch(resp.regex.replace(" ",""), g, re.IGNORECASE)):
            eur = True
            break
        if eur:
          continue
        
        common_guess.append({'txt': g, 'teams': c})
        if len(common_guess) > 9 :
          break
        

      context = {'hunt': {'hunt_name':hunt.hunt_name, 'display_start_date': hunt.display_start_date}, 'data':data, 'name': puz.puzzle_name, 'common_guess': common_guess }
      
      # write json
      with open(filename, 'w') as outfile:
        json.dump(context, outfile, cls=DjangoJSONEncoder)
        
        
    return render(request, 'stats/puzzle.html', context)


@login_required
def charts(request):
    ''' CHARTSSSS: progress of all teams with toggles / top teams, spam contest by user / team , top / average teams time for each puzzle '''
    hunt = get_last_hunt_or_none(request)
    if hunt == None:
      context = {'hunt': None}
      return render(request, 'stats/charts.html', context)



    # load json if exists & non staff
    template_filename =  'stats/static/charts.json'
    filename =  'hunts/templates/' + template_filename

    if ((not request.user.is_staff or not UPDATE_STATS) and os.path.exists(filename)):
      with open(filename) as json_file:
        context = json.load(json_file)
    
    else:        
    
      spams = list(Guess.objects.filter(puzzle__episode__hunt=hunt).values(name=F('user__username' )).annotate(c=Count('name')).order_by('-c')[:10])
      spam_teams = list(Guess.objects.filter(puzzle__episode__hunt=hunt).values(team_name=F('team__team_name'),team_iid=F('team')).annotate(c=Count('team_name')).order_by('-c')[:10])



      # Chart solve over time
      solve_time = []
      teams = Team.objects.filter(hunt=hunt)
      teams = teams.annotate(solves=Count('puz_solved')).filter(solves__gt=0)
      teams = teams.annotate(last_time=Max('puzzlesolve__guess__guess_time'))
      teams = teams.order_by(F('solves').desc(nulls_last=True),
                                     F('last_time').asc(nulls_last=True))
      team_names = teams.values_list('team_name')
                                     
      for ep in hunt.episode_set.order_by('ep_number').all():
        minTime = timezone.now()
        solve_ep = []
        for team in teams:
          solves = team.puzzlesolve_set.filter(puzzle__episode=ep)
          solves = solves.order_by('guess__guess_time')
          if len(solves)>0:
            start_time = solves[0].puzzle.starting_time_for_team(team)
          solves = solves.values_list('guess__guess_time', flat=True)
          if len(solves)>0:
            minTime = min(minTime, start_time)
          solves = [sol.isoformat() for sol in solves]
          
          if len(solves)>0:
            puzzle_limits = [(start_time.isoformat(), solves[0])] + ([ (solves[i],x)  for i, x in enumerate(solves[1:])])
          else:
            puzzle_limits = []

          solves += [None] * (ep.puzzle_set.count() - len(solves))
          solve_ep.append({'solve': solves, 'name': team.team_name, 'puz_limits': puzzle_limits})
        names = ep.puzzle_set.values_list('puzzle_name',flat=True)
        solve_time.append({'solve': solve_ep, 'names': list(names), 'min': minTime.isoformat(), 'teams': list(team_names)})


      #Chart fast / average puzzle solves
      puzzle_list = [puzzle for episode in hunt.episode_set.order_by('ep_number').all() for puzzle in episode.puzzle_set.all()]

      data_puz = []
      for puz in puzzle_list:
        solves = PuzzleSolve.objects.filter(puzzle=puz).order_by('duration')
        dic = solves.aggregate(av_dur= Avg('duration'), min_dur = Min('duration'))
        if len(solves)>0:
          dic =  {'av_dur': datetime.fromtimestamp(dic['av_dur'].total_seconds(), timezone.utc).isoformat()[:-13] , 
          'min_dur': datetime.fromtimestamp(dic['min_dur'].total_seconds(), timezone.utc).isoformat()[:-13],
          'med_dur': datetime.fromtimestamp(solves[math.floor(solves.count()/2-1)].duration.total_seconds(), timezone.utc).isoformat()[:-13],
          'name': puz.puzzle_name}
        else:
          dic =  {'av_dur': None, 'min_dur': None,  'name': puz.puzzle_name, 'med_dur': None}
        data_puz.append(dic)
    
      context = { 'hunt': {'hunt_name':hunt.hunt_name, 'display_start_date': hunt.display_start_date}, 'spammers' : spams, 'spam_teams': spam_teams, 'solve_time':solve_time, 'data_puz': data_puz}
    
      # write json
      with open(filename, 'w') as outfile:
        json.dump(context, outfile, cls=DjangoJSONEncoder)

    return render(request, 'stats/charts.html', context)
