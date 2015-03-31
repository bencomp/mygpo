(
# This file is part of my.gpodder.org.
#
# my.gpodder.org is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# my.gpodder.org is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public
# License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with my.gpodder.org. If not, see <http://www.gnu.org/licenses/>.
#

from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.contrib.auth import logout
from django.utils.translation import ugettext as _
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import RequestSite
from django.views.decorators.vary import vary_on_cookie
from django.views.decorators.cache import never_cache, cache_control
from django.utils.decorators import method_decorator
from django.views.generic.base import View
from django.utils.html import strip_tags

from mygpo.api import APIView
from mygpo.podcasts.models import Podcast
from mygpo.usersettings.models import UserSettings
from mygpo.web.forms import UserAccountForm, ProfileForm, FlattrForm
from mygpo.web.utils import normalize_twitter
from mygpo.flattr import Flattr
from mygpo.users.settings import PUBLIC_SUB_USER, PUBLIC_SUB_PODCAST, \
         FLATTR_TOKEN, FLATTR_AUTO, FLATTR_MYGPO, FLATTR_USERNAME



class ProfileData(APIView):

    @login_required
    @vary_on_cookie
    @cache_control(private=True)
    def get(self, request):

        profile_form = ProfileForm({
               'twitter': request.user.profile.twitter,
               'about':   request.user.profile.about,
            })

        form = UserAccountForm({
        'email': request.user.email,
        'public': request.user.profile.settings.get_wksetting(PUBLIC_SUB_USER)
        })

    def post(self, request):
        form = UserAccountForm(request.POST)

        if not form.is_valid():
            raise ValueError(_('Oops! Something went wrong. Please double-check the data you entered.'))

        if form.cleaned_data['password_current']:
            if not request.user.check_password(form.cleaned_data['password_current']):
                raise ValueError('Current password is incorrect')

            request.user.set_password(form.cleaned_data['password1'])

        request.user.email = form.cleaned_data['email']

        request.user.save()


class FlattrSettings(APIView):

    def get(self, request):
        flattr = Flattr(request.user, site.domain, request.is_secure())

        flattr_form = FlattrForm({
               'enable': request.user.profile.settings.get_wksetting(FLATTR_AUTO),
               'token': request.user.profile.settings.get_wksetting(FLATTR_TOKEN),
               'flattr_mygpo': request.user.profile.settings.get_wksetting(FLATTR_MYGPO),
               'username': request.user.profile.settings.get_wksetting(FLATTR_USERNAME),
            })


class ProfileView(View):
    """ Updates the public profile and redirects back to the account view """

    def post(self, request):
        user = request.user

        form = ProfileForm(request.POST)

        if not form.is_valid():
            raise ValueError(_('Oops! Something went wrong. Please double-check the data you entered.'))

        request.user.twitter = normalize_twitter(form.cleaned_data['twitter'])
        request.user.about = strip_tags(form.cleaned_data['about'])

        request.user.save()

        return HttpResponseRedirect(reverse('account') + '#profile')


class FlattrSettingsView(View):
    """ Updates Flattr settings and redirects back to the Account page """

    def post(self, request):
        user = request.user

        form = FlattrForm(request.POST)

        if not form.is_valid():
            raise ValueError('asdf')

        auto_flattr = form.cleaned_data.get('enable', False)
        flattr_mygpo = form.cleaned_data.get('flattr_mygpo', False)
        username = form.cleaned_data.get('username', '')

        settings = user.profile.settings
        settings.set_wksetting(FLATTR_AUTO, auto_flattr)
        settings.set_wksetting(FLATTR_MYGPO, flattr_mygpo)
        settings.set_wksetting(FLATTR_USERNAME, username)
        settings.save()

        return HttpResponseRedirect(reverse('account') + '#flattr')


class FlattrLogout(View):
    """ Removes Flattr authentication token """

    def get(self, request):
        user = request.user
        settings = user.profile.settings
        settings.set_wksetting(FLATTR_AUTO, False)
        settings.set_wksetting(FLATTR_TOKEN, False)
        settings.set_wksetting(FLATTR_MYGPO, False)
        settings.save()
        return HttpResponseRedirect(reverse('account') + '#flattr')


class FlattrTokenView(View):
    """ Callback for the Flattr authentication

    Updates the user's Flattr token and redirects back to the account page """

    @method_decorator(login_required)
    def get(self, request):

        user = request.user
        site = RequestSite(request)
        flattr = Flattr(user, site.domain, request.is_secure())

        url = request.build_absolute_uri()
        token = flattr.process_retrieved_code(url)
        if token:
            settings = user.profile.settings
            settings.set_wksetting(FLATTR_TOKEN, token)
            settings.save()

        else:
            # raise messages.error(request, _('Authentication failed. Try again later'))

        return HttpResponseRedirect(reverse('account') + '#flattr')


class AccountRemoveGoogle(View):
    """ Removes the connected Google account """

    @method_decorator(login_required)
    def post(self, request):
        request.user.google_email = None
        request.user.save()
        return HttpResponseRedirect(reverse('account'))


class DeleteAccount(APIView):
    @login_required
    @never_cache
    def post(self, request):
        user = request.user
        user.is_active = False
        user.deleted = True
        user.save()
        logout(request)


class DefaultPrivacySettings(View):

    public = True

    @method_decorator(login_required)
    @method_decorator(never_cache)
    def post(self, request):
        settings = request.user.profile.settings
        settings.set_setting(PUBLIC_SUB_USER.name, self.public)
        settings.save()
        return HttpResponseRedirect(reverse('privacy'))


class PodcastPrivacySettings(View):

    public = True

    @method_decorator(login_required)
    @method_decorator(never_cache)
    def post(self, request, podcast_id):
        podcast = Podcast.objects.get(id=podcast_id)

        settings, created = UserSettings.objects.get_or_create(
            user=request.user,
            content_type=ContentType.objects.get_for_model(podcast),
            object_id=podcast.pk,
        )

        settings.set_wksetting(PUBLIC_SUB_PODCAST, self.public)
        settings.save()
        return HttpResponseRedirect(reverse('privacy'))


class SubscriptionPrivacySettings(APIView):
    @login_required
    @never_cache
    def get(self, request):
        user = request.user
        podcasts = Podcast.objects.filter(subscription__user=user)\
                                  .distinct('pk')
        private = UserSettings.objects.get_private_podcasts(user)

        subscriptions = []
        for podcast in podcasts:
            subscriptions.append( (podcast, podcast in private) )

        return {
            'private_subscriptions': not request.user.profile.settings.get_wksetting(PUBLIC_SUB_USER),
            'subscriptions': subscriptions,
        }
