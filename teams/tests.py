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

from django.test import TestCase, override_settings
from django.urls import reverse
from teams import models, forms, templatetags
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta

try:
    from SimpleHTTPServer import SimpleHTTPRequestHandler
except ImportError:
    from http.server import SimpleHTTPRequestHandler
try:
    from SocketServer import TCPServer as HTTPServer
except ImportError:
    from http.server import HTTPServer
from threading import Thread

# python manage.py dumpdata --indent=4  --exclude=contenttypes --exclude=sessions --exclude=admin
# --exclude=auth.permission

# Users: admin, user1, user2, user3, user4, user5, user6
#   admin is superuser/staff and on no teams
#   user1 is on teams 2, 6, 8 (1-2, 2-3, 3-2)
#   user2 is on teams 2, 6, 9 (1-2, 2-3, 3-3) # Reserved for ratelimiting
#   user3 is on teams 3, 5    (1-3, 2-2     )
#   user4 is on teams 3, 4    (1-3, 2-1     )
#   user5 is on teams    6    (     2-3     )
#   user6 is not on any teams

# 3 Hunts: hunt 1 is in the past, hunt 2 is current and running, hunt 3 is in the future
#   Hunt 1: Team limit of 5
#   Hunt 2: Team limit of 3
#   Hunt 3: Team limit of 3

# 3 puzzles per hunt
# 3 teams per hunt, in each hunt, second team is a playtesting team


def login(test, username):
    test.assertTrue(test.client.login(username=username, password='password'))


def get_and_check_page(test, page, code, args={}):
    response = test.client.get(reverse(page, kwargs=args))
    test.assertEqual(response.status_code, code)
    return response


def ajax_and_check_page(test, page, code, args={}):
    response = test.client.get(reverse(page), args,
                               **{'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'})
    test.assertEqual(response.status_code, code)
    return response


def message_from_response(response):
    messages = list(response.context['messages'])
    if(len(messages) > 0):
        return str(messages[0])
    else:
        return ""


def solve_puzzle_from_admin(test):
    test.client.logout()
    login(test, 'user5')
    post_context = {'answer': "wrong answer"}
    response = test.client.post(reverse('puzzle', kwargs={"puzzle_id": "201"}),
                                post_context)
    test.assertEqual(response.status_code, 200)
    post_context = {'answer': "ANSWER21"}
    response = test.client.post(reverse('puzzle', kwargs={"puzzle_id": "201"}),
                                post_context)
    test.assertEqual(response.status_code, 200)
    post_context = {'answer': "wrong answer"}
    response = test.client.post(reverse('puzzle', kwargs={"puzzle_id": "202"}),
                                post_context)
    test.assertEqual(response.status_code, 200)
    response = test.client.post(reverse('puzzle', kwargs={"puzzle_id": "201"}),
                                post_context)
    test.assertEqual(response.status_code, 200)
    test.client.logout()
    login(test, 'admin')


class nonWebTests(TestCase):
    fixtures = ["basic_hunt"]

    def setUp(self):
        puzzle = models.Puzzle.objects.get(pk=5)
        team = models.Team.objects.get(pk=2)

        models.Guess.objects.create(team=team, guess_time=timezone.now(), puzzle=puzzle,
                                         guess_text="foobar", modified_date=timezone.now())
        models.PuzzleSolve.objects.create(puzzle=puzzle, team=team,
                                    guess=models.Guess.objects.all()[0])
        models.TeamPuzzleLink.objects.create(puzzle=puzzle, team=team, time=timezone.now())
        models.Unlockable.objects.create(puzzle=puzzle, content_type="TXT", content="foobar")

    def test_unicode(self):
        str(models.Hunt.objects.all()[0])
        str(models.Puzzle.objects.all()[0])
        str(models.Person.objects.all()[0])
        # str(models.Person.objects.all()[-1])
        str(models.Guess.objects.all()[0])
        str(models.PuzzleSolve.objects.all()[0])
        str(models.TeamPuzzleLink.objects.all()[0])
        str(models.Unlockable.objects.all()[0])
        str(models.Eureka.objects.all()[0])
        # str(models.HuntAssetFile.objects.all()[0])

    def test_hunt_cleaning(self):
        with self.assertRaises(ValidationError):
            hunt = models.Hunt.objects.get(is_current_hunt=True)
            hunt.is_current_hunt = False
            hunt.save()

    def test_bootstrap_tag(self):
        templatetags.bootstrap_tags.active_page(None, None)
        # Try to cover Resolver404 case


class InfoTests(TestCase):
    fixtures = ["basic_hunt"]

    def test_index(self):
        "Test the index page"
        response = get_and_check_page(self, 'index', 200)
        self.assertTrue(isinstance(response.context['curr_hunt'], models.Hunt))

    def test_previous_hunts(self):
        "Test the previous hunts page"
        response = get_and_check_page(self, 'previous_hunts', 200)
        self.assertTrue('hunts' in response.context)
        for hunt in response.context['hunts']:
            self.assertTrue(isinstance(hunt, models.Hunt))

    def test_registration1(self):
        "Test the registration page when not logged in"
        response = get_and_check_page(self, 'registration', 200)
        self.assertEqual(message_from_response(response), "")

    def test_registration2(self):
        "Test the registration page when logged in and on a team"
        login(self, 'user1')
        response = get_and_check_page(self, 'registration', 200)
        self.assertTrue('registered_team' in response.context)
        self.assertTrue(isinstance(response.context['registered_team'], models.Team))

    def test_registration3(self):
        "Test the registration page when logged in and not on a team"
        login(self, 'user6')
        response = get_and_check_page(self, 'registration', 200)
        self.assertEqual(message_from_response(response), "")
        self.assertTrue('teams' in response.context)
        for hunt in response.context['teams']:
            self.assertTrue(isinstance(hunt, models.Team))

    def test_registration_post_new(self):
        "Test the registration page's join team functionality"
        login(self, 'user6')
        post_context = {"form_type": "new_team", "team_name": "new_team",
                        "need_room": "need_a_room"}
        response = self.client.post(reverse('registration'), post_context)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['user'].person.teams.all()), 1)
        team = response.context['user'].person.teams.all()[0]
        self.assertEqual(response.context['registered_team'], team)
        self.assertEqual(team.team_name, post_context['team_name'])
        self.assertEqual(team.location, post_context['need_room'])
        self.assertEqual(team.hunt, models.Hunt.objects.get(is_current_hunt=True))
        self.assertEqual(team.playtester, False)
        self.assertTrue(len(team.join_code) >= 5)

    def test_registration_post_join(self):
        "Test the registration page's new team functionality"
        login(self, 'user6')
        post_context = {"form_type": "join_team", "team_name": "Team2-2",
                        "join_code": "JOIN5"}
        response = self.client.post(reverse('registration'), post_context)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['user'].person.teams.all()), 1)
        team = response.context['user'].person.teams.all()[0]
        self.assertEqual(response.context['registered_team'], team)
        self.assertEqual(team.team_name, post_context['team_name'])
        self.assertEqual(team.hunt, models.Hunt.objects.get(is_current_hunt=True))
        self.assertEqual(len(team.person_set.all()), 2)

    def test_registration_post_leave(self):
        "Test the registration page's leave team functionality"
        login(self, 'user5')
        post_context = {"form_type": "leave_team"}
        response = self.client.post(reverse('registration'), post_context)
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(message_from_response(response), "")
        hunt = models.Hunt.objects.get(is_current_hunt=True)
        self.assertEqual(len(response.context['user'].person.teams.filter(hunt=hunt)), 0)
        self.assertEqual(len(models.Team.objects.get(team_name="Team2-3").person_set.all()), 2)
        login(self, 'user4')
        hunt.start_date = hunt.start_date + timedelta(days=10000)
        hunt.end_date = hunt.end_date + timedelta(days=10000)
        hunt.save()
        post_context = {"form_type": "leave_team"}
        response = self.client.post(reverse('registration'), post_context)
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(message_from_response(response), "")
        self.assertEqual(len(response.context['user'].person.teams.filter(hunt=hunt)), 0)

    def test_registration_post_change_location(self):
        "Test the registration page's new location functionality"
        login(self, 'user4')
        post_context = {"form_type": "new_location", "team_location": "location2.0"}
        response = self.client.post(reverse('registration'), post_context)
        self.assertEqual(response.status_code, 200)
        hunt = models.Hunt.objects.get(is_current_hunt=True)
        team = response.context['user'].person.teams.filter(hunt=hunt)[0]
        self.assertEqual(response.context['registered_team'], team)
        self.assertEqual(team.location, post_context['team_location'])

    def test_registration_post_change_name(self):
        "Test the registration page's new team name functionality"
        login(self, 'user4')
        post_context = {"form_type": "new_name", "team_name": "name 2.0"}
        hunt = models.Hunt.objects.get(is_current_hunt=True)
        hunt.start_date = hunt.start_date + timedelta(days=10000)
        hunt.end_date = hunt.end_date + timedelta(days=10000)
        hunt.save()
        response = self.client.post(reverse('registration'), post_context)
        self.assertEqual(response.status_code, 200)
        team = response.context['user'].person.teams.filter(hunt=hunt)[0]
        self.assertEqual(response.context['registered_team'], team)
        self.assertEqual(team.team_name, post_context['team_name'])

    def test_registration_post_invalid_data(self):
        "Test the registration page with invalid post data"
        login(self, 'user6')

        post_context = {"form_type": "new_team", "team_name": "team2-2",
                        "need_room": "need_a_room"}
        response = self.client.post(reverse('registration'), post_context)
        self.assertNotEqual(message_from_response(response), "")
        self.assertEqual(response.status_code, 200)

        post_context = {"form_type": "new_team", "team_name": "    ",
                        "need_room": "need_a_room"}
        response = self.client.post(reverse('registration'), post_context)
        self.assertNotEqual(message_from_response(response), "")
        self.assertEqual(response.status_code, 200)

        post_context = {"form_type": "join_team", "team_name": "Team2-3",
                        "join_code": "JOIN5"}
        response = self.client.post(reverse('registration'), post_context)
        self.assertNotEqual(message_from_response(response), "")
        self.assertEqual(response.status_code, 200)

        post_context = {"form_type": "join_team", "team_name": "Team2-2",
                        "join_code": "JOIN0"}
        response = self.client.post(reverse('registration'), post_context)
        self.assertNotEqual(message_from_response(response), "")
        self.assertEqual(response.status_code, 200)

        post_context = {"form_type": "join_team", "team_name": "Team2-3",
                        "join_code": "JOIN6"}
        response = self.client.post(reverse('registration'), post_context)
        self.assertNotEqual(message_from_response(response), "")
        self.assertEqual(response.status_code, 200)

    def test_user_profile(self):
        "Test the user profile page"
        login(self, 'user4')
        response = get_and_check_page(self, 'user_profile', 200)
        self.assertTrue(isinstance(response.context['user_form'], forms.UserForm))
        self.assertTrue(isinstance(response.context['person_form'], forms.PersonForm))

    def test_user_profile_post_update(self):
        "Test the ability to update information on the user profile page"
        login(self, 'user4')
        user = User.objects.get(username="user4")
        post_context = {'first_name': user.first_name, 'last_name': user.last_name,
                        'username': user.username, 'email': 'test@test.com'}
        response = self.client.post(reverse('user_profile'), post_context)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['user'].email, "test@test.com")

    def test_user_profile_post_invalid_data(self):
        "Test the profile page with incorrect data"
        login(self, 'user4')
        user = User.objects.get(username="user4")
        post_context = {'first_name': user.first_name, 'last_name': user.last_name,
                        'username': user.username, 'email': 'user3@example.com'}
        response = self.client.post(reverse('user_profile'), post_context)
        self.assertEqual(response.status_code, 200)

    def test_contact_us(self):
        "Test the contact us page"
        get_and_check_page(self, 'contact_us', 200)


@override_settings(RATELIMIT_ENABLE=False)
class HuntTests(TestCase):
    fixtures = ["basic_hunt"]

    # TODO: find a way to simulate files in new file_fields
    # def test_protected_static(self):
    #     "Test the static file protected view"
    #     login(self, 'user1')
    #     get_and_check_page(self, 'protected_static', 200,
    #                        {"file_path": "/"})
    #     get_and_check_page(self, 'protected_static', 200,
    #                        {"file_path": "puzzles/101/example.pdf"})
    #     get_and_check_page(self, 'protected_static', 404,
    #                        {"file_path": "puzzles/201/example.pdf"})

    def test_hunt_normal(self):
        "Test the basic per-hunt view"
        # Check when logged out
        get_and_check_page(self, 'hunt', 302, {"hunt_num": "2"})

        login(self, 'user4')
        get_and_check_page(self, 'hunt', 200, {"hunt_num": "1"})
        get_and_check_page(self, 'hunt', 200, {"hunt_num": "2"})
        get_and_check_page(self, 'hunt', 302, {"hunt_num": "3"})
        login(self, 'admin')
        get_and_check_page(self, 'hunt', 200, {"hunt_num": "2"})
        login(self, 'user3')
        get_and_check_page(self, 'hunt', 200, {"hunt_num": "2"})
        login(self, 'user6')
        get_and_check_page(self, 'hunt', 200, {"hunt_num": "2"})

    def test_current_hunt(self):
        "Test the current hunt redirect"
        login(self, 'user1')
        get_and_check_page(self, 'current_hunt', 200)

    def test_puzzle_normal(self):
        "Test the basic per-puzzle view"
        # Check when logged out
        response = get_and_check_page(self, 'puzzle', 302, {"puzzle_id": "201"})

        login(self, 'user4')
        response = get_and_check_page(self, 'puzzle', 200, {"puzzle_id": "101"})

        post_context = {'answer': "Wrong Answer"}
        response = self.client.post(reverse('puzzle',
                                            kwargs={"puzzle_id": "101"}),
                                    post_context)
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse('puzzle',
                                            kwargs={"puzzle_id": "101"}))
        self.assertEqual(response.status_code, 200)

        response = get_and_check_page(self, 'puzzle', 200, {"puzzle_id": "201"})

        post_context = {'answer': "Wrong Answer"}
        response = self.client.post(reverse('puzzle',
                                            kwargs={"puzzle_id": "201"}),
                                    post_context)
        self.assertEqual(response.status_code, 200)

        post_context = {'answer': "ANSWER21"}
        response = self.client.post(reverse('puzzle',
                                            kwargs={"puzzle_id": "201"}),
                                    post_context)
        self.assertEqual(response.status_code, 200)

        post_context = {'answer': "almost"}
        response = self.client.post(reverse('puzzle',
                                            kwargs={"puzzle_id": "202"}),
                                    post_context)
        self.assertEqual(response.status_code, 200)

        post_context = {'answer': "answer22"}
        response = self.client.post(reverse('puzzle',
                                            kwargs={"puzzle_id": "202"}),
                                    post_context)
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse('puzzle', kwargs={"puzzle_id": "201"}),
                                   {'last_date': '2000-01-01T01:01:01.001Z'},
                                   **{'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'})
        self.assertEqual(response.status_code, 200)

    @override_settings(RATELIMIT_ENABLE=True)
    def test_puzzle_ratelimit(self):
        "Test that users are properly ratelimited"
        login(self, 'user2')
        post_context = {'answer': "Wrong Answer"}
        for i in range(20):
            response = self.client.post(reverse('puzzle', kwargs={"puzzle_id": "101"}),
                                        post_context)
        response = self.client.post(reverse('puzzle', kwargs={"puzzle_id": "101"}),
                                    post_context)
        self.assertEqual(response.status_code, 403)

    def test_unlockables(self):
        "Test the unlockables view"
        login(self, 'user1')
        response = get_and_check_page(self, 'unlockables', 200)
        login(self, 'user6')
        response = get_and_check_page(self, 'unlockables', 200)
        self.assertTemplateUsed(response, 'access_error.html')


@override_settings(USE_SHIBBOLETH=False)
class AuthTests(TestCase):
    fixtures = ["basic_hunt"]

    def test_register(self):
        "Test the account creation view"
        response = get_and_check_page(self, 'register', 200)
        post_context = {'user-first_name': "first", 'user-last_name': "last",
                        'user-username': "user7",
                        'user-email': 'user7@example.com',
                        'user-password': "password",
                        'user-confirm_password': "password"}

        post_context['user-email'] = "user6@example.com"
        response = self.client.post(reverse('register'), post_context)
        self.assertEqual(response.status_code, 200)
        post_context['user-email'] = "user7@example.com"

        post_context['user-username'] = "$$$"
        response = self.client.post(reverse('register'), post_context)
        self.assertEqual(response.status_code, 200)
        post_context['user-username'] = "user7"

        post_context['user-confirm_password'] = "wordpass"
        response = self.client.post(reverse('register'), post_context)
        self.assertEqual(response.status_code, 200)
        post_context['user-confirm_password'] = "password"

        response = self.client.post(reverse('register'), post_context)
        self.assertEqual(response.status_code, 200)

    def test_login_selection(self):
        "Test the login selection view"
        response = get_and_check_page(self, 'login_selection', 200)
        response = self.client.get(reverse('login_selection'), {'next': '/'})
        self.assertEqual(response.status_code, 200)

    def test_account_logout(self):
        "Test the account logout view"
        login(self, 'user1')
        response = get_and_check_page(self, 'account_logout', 200)
        login(self, 'user1')
        response = self.client.get(reverse('account_logout'), {'next': '/'})
        self.assertEqual(response.status_code, 200)


@override_settings(RATELIMIT_ENABLE=False)
class StaffTests(TestCase):
    fixtures = ["basic_hunt"]

    def test_staff_queue(self):
        "Test the staff queue view"
        login(self, 'admin')
        response = get_and_check_page(self, 'queue', 200)

        response = ajax_and_check_page(self, 'queue', 200,
                                       {'last_date': '2000-01-01T01:01:01.001Z'})

        puzzle = models.Puzzle.objects.all()[0]
        team = models.Team.objects.all()[0]
        s = models.Guess.objects.create(guess_text="bad answer", puzzle=puzzle,
                                             guess_time=timezone.now(), team=team)
        post_context = {'response': "Wrong answer", 'sub_id': str(s.pk)}
        response = self.client.post(reverse('queue'), post_context)
        self.assertEqual(response.status_code, 200)

        post_context = {'response': "Wrong answer", 'sub_id': ""}
        response = self.client.post(reverse('queue'), post_context)
        self.assertEqual(response.status_code, 400)

    def test_staff_queue_args(self):
        "Test the staff paged queue view"
        login(self, 'admin')
        response = self.client.get(reverse('queue'),
                                   {"page_num": "1", "team_id": "18", "puzzle_id": "12"})
        self.assertEqual(response.status_code, 200)

    def test_staff_progress(self):
        "Test the staff progress view"
        login(self, 'admin')
        response = get_and_check_page(self, 'progress', 200)
        ajax_args = {'last_solve_pk': '0', 'last_guess_pk': '0', 'last_unlock_pk': '0'}
        response = ajax_and_check_page(self, 'progress', 200, ajax_args)
        response = ajax_and_check_page(self, 'progress', 404, {'last_solve_pk': '1'})
        solve_puzzle_from_admin(self)
        response = ajax_and_check_page(self, 'progress', 200, ajax_args)
        response = get_and_check_page(self, 'progress', 200)

        post_context = {'action': "unlock", 'team_id': "5", 'puzzle_id': "202"}
        response = self.client.post(reverse('progress'), post_context)
        self.assertEqual(response.status_code, 200)

        post_context = {'action': "unlock", 'team_id': "5", 'puzzle_id': "202"}
        response = self.client.post(reverse('progress'), post_context)
        self.assertEqual(response.status_code, 200)

        post_context = {'action': "unlock_all", 'puzzle_id': "5"}
        response = self.client.post(reverse('progress'), post_context)
        self.assertEqual(response.status_code, 200)

        post_context = {}
        response = self.client.post(reverse('progress'), post_context)
        self.assertEqual(response.status_code, 400)

    def test_staff_charts(self):
        "Test the staff charts view"

        login(self, 'admin')
        get_and_check_page(self, 'charts', 200)
        solve_puzzle_from_admin(self)
        get_and_check_page(self, 'charts', 200)

    def test_staff_control(self):
        "Test the staff control view"

        class NoLogHandler(SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                return

        server = HTTPServer(("localhost", 8898), NoLogHandler)

        mock_server_thread = Thread(target=server.serve_forever)
        mock_server_thread.setDaemon(True)
        mock_server_thread.start()

        login(self, 'admin')
        post_context = {'action': "initial"}
        response = self.client.post(reverse('control'), post_context)
        self.assertEqual(response.status_code, 302)
        post_context = {'action': "reset"}
        response = self.client.post(reverse('control'), post_context)
        self.assertEqual(response.status_code, 302)
        # post_context = {'action': "getpuzzles", "hunt_number": "1"}
        # response = self.client.post(reverse('control'), post_context)
        # self.assertEqual(response.status_code, 200)
        # post_context = {'action': "getpuzzles", "puzzle_number": "1", "puzzle_id": "201"}
        # response = self.client.post(reverse('control'), post_context)
        # self.assertEqual(response.status_code, 200)
        post_context = {'action': "new_current_hunt", "hunt_number": "1"}
        response = self.client.post(reverse('control'), post_context)
        self.assertEqual(response.status_code, 302)
        post_context = {'action': "foobar"}
        response = self.client.post(reverse('control'), post_context)
        self.assertEqual(response.status_code, 404)

    def test_staff_emails(self):
        "Test the staff email view"
        login(self, 'admin')
        response = get_and_check_page(self, 'emails', 200)

        post_context = {'subject': "test_subject", 'message': "test_message"}
        response = self.client.post(reverse('emails'), post_context)
        self.assertEqual(response.status_code, 302)

    def test_staff_management(self):
        "Test the staff management view"
        login(self, 'admin')
        get_and_check_page(self, 'hunt_management', 200)

    def test_staff_info(self):
        "Test the staff info view"
        login(self, 'admin')
        get_and_check_page(self, 'hunt_info', 200)

    def test_admin_pages(self):
        "Test the admin page for team objects"
        login(self, 'admin')
        response = self.client.get(reverse('admin:teams_team_change', args=(1,)))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('admin:teams_puzzle_change', args=(1,)))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('admin:teams_hunt_change', args=(1,)))
        self.assertEqual(response.status_code, 200)


"""
admin.py
Saving models

hunt_views.py
puzzle view guess with no team
puzzle view guess with excecption case?
puzzle view ajax with no team
puzzle view ajax with exception case?
chat view ajax something about messages?

info_views.py
registration view with team name update

models.py
check if serialize for ajax is still needed/used (if so, use it)
unicode on all models

staff_views.py
queue page exceptions (not possible?)
progress ajax as non-staff (not possible?)
progress normal page with no guesss

bootstrap_tags.py
call the tag with bad data?

utils.py
download puzzles but directory doesn't exist
values exception in parse_attributes


Plan:
- Attempt P2.7, P3.6, D1.8 D1.9 D1.10 D1.11 D1.12 D2.0 D2.1
- Fix things until step 3 works
"""
