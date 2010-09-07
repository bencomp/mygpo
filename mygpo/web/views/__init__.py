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

from django.http import HttpResponseRedirect, Http404
from django.contrib.auth.models import User
from django.template import RequestContext
from mygpo.api.models import Podcast, Episode, Device, EpisodeAction, SubscriptionAction, ToplistEntry, Subscription, SuggestionEntry, UserProfile
from mygpo.data.models import Listener, SuggestionBlacklist, PodcastTag
from mygpo.web.models import Rating
from mygpo.decorators import manual_gc
from django.contrib.auth.decorators import login_required
from django.shortcuts import render_to_response
from django.db.models import Sum
from datetime import datetime
from django.contrib.sites.models import Site
from mygpo.constants import PODCAST_LOGO_SIZE, PODCAST_LOGO_BIG_SIZE
from mygpo.web import utils
from mygpo.api import backend
import os
import Image
import ImageDraw
import StringIO


def home(request):
    if request.user.is_authenticated():
        return dashboard(request)
    else:
        return welcome(request)


@manual_gc
def welcome(request, toplist_entries=10):
    current_site = Site.objects.get_current()
    podcasts = Podcast.objects.count()
    users = User.objects.filter(is_active=True).count()
    episodes = Episode.objects.count()
    hours_listened = Listener.objects.all().aggregate(hours=Sum('episode__duration'))['hours'] / (60 * 60)

    try:
        lang = utils.process_lang_params(request, '/toplist/')
    except utils.UpdatedException, updated:
        lang = []

    if len(lang) == 0:
        entries = ToplistEntry.objects.all()[:toplist_entries]
    else:
        entries = backend.get_toplist(toplist_entries, lang)

    toplist = [e.get_podcast() for e in entries]
    sponsored_podcast = utils.get_sponsored_podcast()

    return render_to_response('home.html', {
          'podcast_count': podcasts,
          'user_count': users,
          'episode_count': episodes,
          'url': current_site,
          'hours_listened': hours_listened,
          'toplist': toplist,
          'sponsored_podcast': sponsored_podcast,
    }, context_instance=RequestContext(request))


@manual_gc
@login_required
def dashboard(request, episode_count=10):
    site = Site.objects.get_current()
    devices = Device.objects.filter(user=request.user, deleted=False)
    subscribed_podcasts = set([s.podcast for s in Subscription.objects.filter(user=request.user)])
    newest_episodes = Episode.objects.filter(podcast__in=subscribed_podcasts).order_by('-timestamp')[:episode_count]

    lang = utils.get_accepted_lang(request)
    lang = utils.sanitize_language_codes(lang)

    random_podcasts = backend.get_random_picks(lang)[:5]
    sponsored_podcast = utils.get_sponsored_podcast()

    return render_to_response('dashboard.html', {
            'site': site,
            'devices': devices,
            'subscribed_podcasts': subscribed_podcasts,
            'newest_episodes': newest_episodes,
            'random_podcasts': random_podcasts,
            'sponsored_podcast': sponsored_podcast,
        }, context_instance=RequestContext(request))


def cover_art(request, size, filename):
    size = int(size)
    if size not in (PODCAST_LOGO_SIZE, PODCAST_LOGO_BIG_SIZE):
        raise Http404('Wrong size')

    # XXX: Is there a "cleaner" way to get the root directory of the installation?
    root = os.path.join(os.path.dirname(__file__), '..', '..', '..')
    target = os.path.join(root, 'htdocs', 'media', 'logo', str(size), filename+'.jpg')
    filepath = os.path.join(root, 'htdocs', 'media', 'logo', filename)

    if os.path.exists(target):
        return HttpResponseRedirect('/media/logo/%s/%s.jpg' % (str(size), filename))

    if os.path.exists(filepath):
        target_dir = os.path.dirname(target)
        if not os.path.isdir(target_dir):
            os.makedirs(target_dir)

        try:
            im = Image.open(filepath)
            if im.mode not in ('RGB', 'RGBA'):
                im = im.convert('RGB')
        except:
            raise Http404('Cannot open cover file')

        try:
            resized = im.resize((size, size), Image.ANTIALIAS)
        except IOError:
            # raised when trying to read an interlaced PNG; we use the original instead
            return HttpResponseRedirect('/media/logo/%s' % filename)

        # If it's a RGBA image, composite it onto a white background for JPEG
        if resized.mode == 'RGBA':
            background = Image.new('RGB', resized.size)
            draw = ImageDraw.Draw(background)
            draw.rectangle((-1, -1, resized.size[0]+1, resized.size[1]+1), \
                    fill=(255, 255, 255))
            del draw
            resized = Image.composite(resized, background, resized)

        io = StringIO.StringIO()
        resized.save(io, 'JPEG', optimize=True, progression=True, quality=80)
        s = io.getvalue()

        fp = open(target, 'wb')
        fp.write(s)
        fp.close()

        return HttpResponseRedirect('/media/logo/%s/%s.jpg' % (str(size), filename))
    else:
        raise Http404('Cover art not available')

@manual_gc
def history(request, len=15, device_id=None):
    if device_id:
        devices = Device.objects.filter(id=device_id)
    else:
        devices = Device.objects.filter(user=request.user)

    history = SubscriptionAction.objects.filter(device__in=devices).order_by('-timestamp')[:len]
    episodehistory = EpisodeAction.objects.filter(device__in=devices).order_by('-timestamp')[:len]

    generalhistory = []

    for row in history:
        generalhistory.append(row)
    for row in episodehistory:
        generalhistory.append(row)

    generalhistory.sort(key=lambda x: x.timestamp,reverse=True)

    return render_to_response('history.html', {
        'generalhistory': generalhistory,
        'singledevice': devices[0] if device_id else None
    }, context_instance=RequestContext(request))


@manual_gc
@login_required
def suggestions(request):

    rated = False

    if 'rate' in request.GET:
        Rating.objects.create(target='suggestions', user=request.user, rating=request.GET['rate'], timestamp=datetime.now())
        rated = True

    if 'blacklist' in request.GET:
        try:
            blacklisted_podcast = Podcast.objects.get(id=request.GET['blacklist'])
            SuggestionBlacklist.objects.create(user=request.user, podcast=blacklisted_podcast)

            p, _created = UserProfile.objects.get_or_create(user=request.user)
            p.suggestion_up_to_date = False
            p.save()

        except Exception, e:
            print e


    entries = SuggestionEntry.objects.for_user(request.user)
    current_site = Site.objects.get_current()
    return render_to_response('suggestions.html', {
        'entries': entries,
        'rated'  : rated,
        'url': current_site
    }, context_instance=RequestContext(request))


@login_required
def mytags(request):
    tags_podcast = {}
    tags_tag = {}
    for tag in PodcastTag.objects.filter(user=request.user):
        if not tag.podcast in tags_podcast:
            tags_podcast[tag.podcast] = []

        if not tag.tag in tags_tag:
            tags_tag[tag.tag] = []

        tag.is_own = True
        tags_podcast[tag.podcast].append(tag)
        tags_tag[tag.tag].append(tag)

    return render_to_response('mytags.html', {
        'tags_podcast': tags_podcast,
        'tags_tag': tags_tag,
    }, context_instance=RequestContext(request))
