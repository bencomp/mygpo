#
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

import sys
from collections import defaultdict
from datetime import datetime, timedelta

from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.contrib import messages
from django.utils.translation import ugettext as _
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.contrib.sites.models import RequestSite
from django.views.generic.base import View
from django.views.decorators.vary import vary_on_cookie
from django.views.decorators.cache import never_cache, cache_control

from mygpo.podcasts.models import Podcast, Episode, Tag
from mygpo.users.models import HistoryEntry, Client
from mygpo.subscriptions import get_subscribed_podcasts
from mygpo.web.utils import process_lang_params
from mygpo.utils import parse_range
from mygpo.podcastlists.models import PodcastList
from mygpo.favorites.models import FavoriteEpisode
from mygpo.users.settings import FLATTR_AUTO, FLATTR_TOKEN
from mygpo.api import APIView
from mygpo.publisher.models import PublishedPodcast


@vary_on_cookie
@cache_control(private=True)
@login_required
def dashboard(request, episode_count=10):

    subscribed_podcasts = get_subscribed_podcasts(request.user)
    subscribed_podcasts = [sp.podcast for sp in subscribed_podcasts]

    site = RequestSite(request)

    checklist = []

    if request.user.client_set.count():
        checklist.append('devices')

    if subscribed_podcasts:
        checklist.append('subscriptions')

    if FavoriteEpisode.objects.filter(user=request.user).exists():
        checklist.append('favorites')

    if not request.user.profile.get_token('subscriptions_token'):
        checklist.append('share')

    if not request.user.profile.get_token('favorite_feeds_token'):
        checklist.append('share-favorites')

    if not request.user.profile.get_token('userpage_token'):
        checklist.append('userpage')

    if Tag.objects.filter(user=request.user).exists():
        checklist.append('tags')

    if PodcastList.objects.filter(user=request.user).exists():
        checklist.append('lists')

    if PublishedPodcast.objects.filter(publisher=request.user).exists():
        checklist.append('publish')

    if request.user.profile.settings.get_wksetting(FLATTR_TOKEN):
        checklist.append('flattr')

    if request.user.profile.settings.get_wksetting(FLATTR_AUTO):
        checklist.append('auto-flattr')

    tomorrow = datetime.today() + timedelta(days=1)

    newest_episodes = Episode.objects.filter(podcast__in=subscribed_podcasts,
                                             released__lt=tomorrow).\
                                      select_related('podcast').\
                                      prefetch_related('slugs',
                                                       'podcast__slugs').\
                                      order_by('-released')[:episode_count]


    # we only show the "install reader" link in firefox, because we don't know
    # yet how/if this works in other browsers.
    # hints appreciated at https://bugs.gpodder.org/show_bug.cgi?id=58
    show_install_reader = \
                'firefox' in request.META.get('HTTP_USER_AGENT', '').lower()

    random_podcast = Podcast.objects.all().random().prefetch_related('slugs').first()

    return render(request, 'dashboard.html', {
            'user': request.user,
            'subscribed_podcasts': subscribed_podcasts,
            'newest_episodes': list(newest_episodes),
            'random_podcast': random_podcast,
            'checklist': checklist,
            'site': site,
            'show_install_reader': show_install_reader,
        })


class MyTags(APIView):
    @vary_on_cookie
    @cache_control(private=True)
    @login_required
    def get(self, request):
        tags_tag = defaultdict(list)

        user = request.user

        tags = Tag.objects.filter(source=Tag.USER, user=user).order_by('tag')
        for tag in tags:
            tags_tag[tag.tag].append(tag.content_object)

        return {
            'tags_tag': dict(tags_tag.items()),
        }
