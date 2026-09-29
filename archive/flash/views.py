# -*- coding: utf-8 -*-
"""xxxflash project, main views"""

from datetime import datetime
import ipaddr as ipaddress

import json as simplejson
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, HttpResponse, \
    HttpResponseNotFound, Http404
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache, cache_page
from django.core.exceptions import ValidationError, NON_FIELD_ERRORS
from django.core.mail import mail_admins
from django.core.paginator import Paginator, InvalidPage, \
    EmptyPage, PageNotAnInteger
from django.db.models import F
from django.core.urlresolvers import reverse
from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib.auth import logout
from django.core.mail import send_mail
from django.contrib.auth import authenticate, login

from emailuser.models import EmailUser, EmailUserForm, manual_create_email_user
from djangohelpers.utils import get_page_range
from djangohelpers.utils import gen_url as gen_hash
from djangohelpers import edge

from flash.models import *

#@cache_page(60 * 30)


def index(request):
    """    index page    """

    top_profiles = Profile.objects.all().exclude(
        user__username__exact='Anonymous').order_by("-score")[:5]
    user = request.user

    index_page = True

    try:
        page_id = int(request.GET.get('p', 1))
    except ValueError:
        raise Http404

    if page_id == 1:
        first_page = True

    themes = Theme.objects.filter(active=True, count__gt=0)

    f = Flash.objects.filter(rate__gt=-2,
                             active=True,
                             publication_date__lte=datetime.now()
                             ).order_by(*settings.INDEX_ORDER_BY)
    best = Flash.objects.filter(active=True,
                                publication_date__lte=datetime.now()
                                ).order_by('-rate')[:5]
    random2 = Flash.objects.filter(active=True,
                                   publication_date__lte=datetime.now()
                                   ).order_by('?')[:5]
    random = Flash.objects.filter(active=True,
                                  publication_date__lte=datetime.now()
                                  ).order_by('?')[:7]

    paginator = Paginator(f, settings.GAMES_PER_PAGE)

    try:
        flashes = paginator.page(page_id)
    except EmptyPage:
        flashes = paginator.page(paginator.num_pages)
    pages = get_page_range(paginator, page_id)
    comments_q = Comment.objects.filter().order_by("-id")
    paginator_c = Paginator(comments_q, 5)
    try:
        comments = paginator_c.page(1)
    except EmptyPage:
        comments = paginator_c.page(paginator.num_pages)

    return render(request, "index.html", locals())

#@cache_page(60 * 15)


def theme(request, theme_url):
    theme = get_object_or_404(Theme, url=theme_url)
    user = request.user

    try:
        page_id = int(request.GET.get('p', 1))
    except ValueError:
        raise Http404

    themes = Theme.objects.filter(active=True, count__gt=0)
    f = Flash.objects.filter(theme=theme,
                             active=True,
                             publication_date__lte=datetime.now()
                             ).order_by("-xrate")

    paginator = Paginator(f, 10)
    page_id = int(page_id)
    try:
        flashes = paginator.page(page_id)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        flashes = paginator.page(paginator.num_pages)
    pages = get_page_range(paginator, page_id)
    return render(request, "theme.html", locals())


@never_cache
def game(request, game_id):
    """View game page"""

    is_edge = edge.is_mobile(request)

    random = Flash.objects.filter(active=True,
                                  publication_date__lte=datetime.now()
                                  ).order_by('?')[:7]
    form = CommentForm()
    themes = Theme.objects.filter(active=True, count__gt=0)

    try:
        g = Flash.objects.get(pk=game_id)
    except Flash.DoesNotExist:
        raise Http404
    views = g.views
    user = request.user

    if g.active == False:
        raise Http404
        game_under_moderation = True
        return locals()

    screens = Screenshot.objects.filter(flash=g)
    ref = request.META.get("HTTP_REFERER", '')
    if ref == "":  # bot is here...
        pass
    else:
        gt = g.theme.filter()
        g.views = F('views') + 1
        if views == 0:
            views = 1
        if g.rate > 0:
            g.xrate = (1 / (float(views) / float(g.rate))) * 10000
        else:
            g.xrate = g.rate
        g.save(update_fields=['views', 'xrate'])

    page_id = 1
    comments_q = Comment.objects.filter(flash=g).order_by("-id")

    paginator = Paginator(comments_q, settings.COMMENTS_PER_PAGE)
    try:
        comments = paginator.page(page_id)
    except EmptyPage:
        comments = paginator.page(paginator.num_pages)
    pages = get_page_range(paginator, page_id)

    try:
        m = Mark.objects.get(flash=g)
    except Mark.DoesNotExist:
        mark = "0"
    except Mark.MultipleObjectsReturned:
        Mark.objects.filter(flash=g).delete()
        mark = "0"
    else:
        mark = m.mark

    return render(request, "game.html", locals())


def get_comments(request, game_id, page_id):
    g = get_object_or_404(Flash, pk=game_id)
    page_id = int(page_id)
    comments_q = Comment.objects.filter(flash=g).order_by("-id",)
    paginator = Paginator(comments_q, settings.COMMENTS_PER_PAGE)
    try:
        comments = paginator.page(page_id)
    except EmptyPage:
        comments = paginator.page(paginator.num_pages)
    pages = get_page_range(paginator, page_id)

    return render(request, "comments_list.html", locals())


def ban(request, comment_id):
    comment = get_object_or_404(Comment, pk=comment_id)
    c, i = Ban.objects.get_or_create(ip=comment.ip)
    return HttpResponseRedirect("/?user_was_banned")


@never_cache
@login_required
def add_comment(request):
    ua = request.META.get('HTTP_USER_AGENT', 'No user agent')[:250]
    ip = request.META.get('REMOTE_ADDR', 'No ip')
    is_baned = Ban.objects.filter(ip=ip).count()
    if is_baned > 0:
        return HttpResponseRedirect("http://natribu.org/")

    if request.method == 'POST':
        form = CommentForm(request.POST)
        if form.is_valid():
            if request.POST["email"] != "":
                return HttpResponseRedirect("/")
            comment_text = form.cleaned_data["text"]
            badwords = BannedWord.objects.all()
            for bw in badwords:
                if bw.word.lower() in comment_text.lower():
                    # banned word
                    return HttpResponseRedirect("/")

            user = request.user
            if user.is_authenticated():
                profile = user.profile  # get_profile()
            else:
                profile = None
            if profile is not None:
                profile.score += 3
                profile.save(update_fields=['score'])

            flash = Flash.objects.get(pk__exact=form.cleaned_data["flash_id"])
            c = Comment(text=comment_text, user=user, flash=flash,
                        ip=ip, ua=ua)
            c.save()
            url = reverse('view_game',
                          kwargs={'game_id': form.cleaned_data["flash_id"]})
            return HttpResponseRedirect("%s?new" % url)

        else:
            return HttpResponseRedirect("/")
    else:
        return HttpResponseRedirect("/")
    return locals()


@login_required()
def del_comment(request, comment_id):
    if request.user.is_staff:
        c = Comment.objects.get(id__exact=comment_id)
        user = request.user
        if user.is_authenticated():
            profile = user.profile  # get_profile()
            profile.score = profile.score - 10
            profile.save(update_fields=['score'])
        else:
            profile = None
        c.delete()
    return HttpResponseRedirect('/')


@never_cache
def mark(request):
    results = {'success': False}

    if request.user.is_anonymous():
        user = False
        staf = False
    else:
        user = request.user
        profile = user.profile
        if profile is not None:
            profile.score = profile.score + 1
            profile.save()
        staf = request.user.is_staff
    if request.method == u'GET':
        GET = request.GET
        if GET.has_key(u'pk') and GET.has_key(u'vote'):
            try:
                flash_id = int(GET[u'pk'])
            except ValueError:
                raise Http404
            vote = GET[u'vote']
            if vote == u"up":
                mark = 1
            elif vote == u"down":
                mark = -1
        else:
            return False
    else:
        return False
    flash = Flash.objects.get(pk__exact=flash_id)

    ip_marks = CMark.objects.filter(flash=flash,
                                    ip=request.META['REMOTE_ADDR'])

    if (ip_marks.count() > 0) and (not staf):

        results = {'success': 'Вы уже голосовали'}
        json = simplejson.dumps(results)
        return HttpResponse(json, content_type='application/json')
    else:
        c = CMark(ip=request.META['REMOTE_ADDR'], mark=mark,
                  flash=flash, publication_date=datetime.now())
        c.save()
    m = Mark.objects.filter(flash=flash)
    if m.count() == 1:
        m = Mark.objects.get(flash=flash)
        m.mark = m.mark + mark
        m.save()
        try:
            p = Profile.objects.get(user=flash.user)
        except Profile.DoesNotExist:
            p = None

        if p is not None:
            p.score = p.score + mark
            p.save()

        flash.rate = m.mark
        if flash.rate < -4:
            flash.active = False
        flash.save()
        results = {'success': m.mark}
    elif m.count() > 0:
        results = {'success': 'Error'}
    else:
        m = Mark(flash=flash, mark=mark)
        m.save()
        flash.rate = mark
        flash.save()
        results = {'success': mark}
    json = simplejson.dumps(results)

    return HttpResponse(json, content_type='application/json')

#@cache_page(60 * 15)


def best_games(request):
    base_url = reverse('best')
    themes = Theme.objects.filter(active=True, count__gt=0)
    try:
        page_id = int(request.GET.get('p', 1))
    except ValueError:
        raise Http404

    best = True
    f = Flash.objects.filter(active=True,
                             publication_date__lte=datetime.now()
                             ).order_by("-rate")
    paginator = Paginator(f, settings.BEST_GAMES_COUNT)

    try:
        flashes = paginator.page(page_id)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        flashes = paginator.page(paginator.num_pages)
    pages = get_page_range(paginator, page_id)
    return render(request, "best_and_popular.html", locals())

#@cache_page(60 * 15)


def best_games2(request):
    base_url = reverse('best2')
    themes = Theme.objects.filter(active=True, count__gt=0)
    try:
        page_id = int(request.GET.get('p', 1))
    except ValueError:
        raise Http404

    best = True
    f = Flash.objects.filter(active=True,
                             publication_date__lte=datetime.now()
                             ).order_by("-xrate")
    paginator = Paginator(f, settings.BEST_GAMES_COUNT)

    try:
        flashes = paginator.page(page_id)
    except EmptyPage:
        flashes = paginator.page(paginator.num_pages)
    pages = get_page_range(paginator, page_id)
    return render(request, "best_and_popular.html", locals())

#@cache_page(60 * 15)


def popular_games(request):
    base_url = reverse('popular')
    popular = True
    try:
        page_id = int(request.GET.get('p', 1))
    except ValueError:
        raise Http404

    themes = Theme.objects.filter(active=True, count__gt=0)

    f = Flash.objects.filter(active=True,
                             publication_date__lte=datetime.now()
                             ).order_by("-views")
    paginator = Paginator(f, settings.BEST_GAMES_COUNT)

    try:
        flashes = paginator.page(page_id)
    except EmptyPage:
        flashes = paginator.page(paginator.num_pages)
    pages = get_page_range(paginator, page_id)
    return render(request, "best_and_popular.html", locals())


#@never_cache
def random_games(request):
    themes = Theme.objects.filter(active=True, count__gt=0)
    flashes = Flash.objects.filter(active=True,
                                   publication_date__lte=datetime.now()
                                   ).order_by('?')[:settings.GAMES_PER_PAGE]
    return render(request, "index.html", locals())


def upload_redirect(request):
    return HttpResponseRedirect('/upload/')


@login_required
def upload(request):
    user = request.user
    profile = user.profile  # get_profile()
    themes = Theme.objects.filter(pk__gt=0).order_by('name')
    errors = []
    if request.method == 'POST':
        form = FlashForm(request.POST, request.FILES)
        if form.is_valid():
            name = form.cleaned_data['name']
            theme_names = form.cleaned_data['theme']
            description = form.cleaned_data['description']
            thumbfile = form.cleaned_data['thumbfile']
            flashfile = form.cleaned_data['flashfile']
            user = request.user
            w = Flash(name=name, user=user,  active=False,
                      publication_date=datetime.now(), flashfile=flashfile,
                      rate=0, views=0, thumbfile=thumbfile,
                      description=description, datahash="0")
            try:
                w.full_clean()
            except ValidationError, e:
                errors = e.message_dict[NON_FIELD_ERRORS]
                print errors
            else:
                w.save()
                mail_admins("New flash game was uploaded",
                            "Moderate this game: %s/admin/flash/flash/%s/" %
                            (settings.SITE_URL, w.id))
                if profile is not None:
                    profile.score = profile.score + 10
                    profile.save()
                return HttpResponseRedirect(w.get_absolute_url())
        else:
            render(request, "upload-flash.html", locals())
    else:
        form = FlashForm()
    return render(request, "upload-flash.html", locals())


def search(request, query=False):
    if query == False:
        query = request.GET.get("q", "").strip()[:300]
        if query == "":
            return HttpResponseRedirect("/")
        return HttpResponseRedirect("/search/%s" % query)

    flash_q = Flash.search.query(query).filter()

    paginator = Paginator(flash_q, 20)
    try:
        page_id = int(request.GET.get("p", 1))
    except ValueError:
        raise Http404
    try:
        flashes = paginator.page(page_id)
    except EmptyPage:
        flashes = paginator.page(paginator.num_pages)
    else:
        ref = request.META.get("HTTP_REFERER", '')
        if settings.SITE_BASE in ref:
            try:
                s, c = Search.objects.get_or_create(query=query)
                s.count = F('count') + 1
                s.save()
            except Search.MultipleObjectsReturned:
                Search.objects.filter(query=query).delete()
                s, c = Search.objects.get_or_create(query=query)
                s.count = F('count') + 1
                s.save(update_fields=['count'])

    pages = get_page_range(paginator, page_id)

    return render(request, "search.html", locals())


def index_old(request, page_id):
    url = reverse('index_page')
    return HttpResponseRedirect("%s?p=%s" % (url, page_id))


def theme_old(request, theme_name, page_id):
    url = reverse('theme', kwargs={'theme_url': theme_name})
    return HttpResponseRedirect("%s?p=%s" % (url, page_id))


def best_old(request, page_id):
    url = reverse('best')
    return HttpResponseRedirect("%s?p=%s" % (url, page_id))


def best2_old(request, page_id):
    url = reverse('best2')
    return HttpResponseRedirect("%s?p=%s" % (url, page_id))


def popular_old(request, page_id):
    url = reverse('popular')
    return HttpResponseRedirect("%s?p=%s" % (url, page_id))


def get_user_panel(request):
    user = request.user
    if user.is_authenticated():
        profile = user.profile  # get_profile()
    else:
        profile = None
    return render(request, 'user/panel.html', {'user': user, 'profile': profile})


@never_cache
def auth(request, user_id, token):
    get_user = get_object_or_404(User, pk=user_id)
    user = authenticate(email=get_user.email, token=token)
    if user is not None:
        if user.is_active:
            login(request, user)
    return render(request, "user/auth.html", {"user": user})


@never_cache
def login_view(request):
    sended = False
    if request.method == "POST":
        form = EmailUserForm(request.POST)
        if form.is_valid():  # All validation rules pass
            email = form.cleaned_data['email']
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                username = email.split('@')[0].lower()
                bad_username = True
                while bad_username:
                    try:  # check if username taken already
                        user = User.objects.get(username=username)
                    except User.DoesNotExist:  # good we can use it
                        bad_username = False
                    else:  # gen new username
                        username = "%s_%s" % (username, gen_hash(2))
                password = '%s' % gen_hash(20)
                user = User.objects.create_user(
                    email=form.cleaned_data["email"],
                    username=username,
                    password=password)
                user.save()
            try:
                token = user.emailuser.generate_token()
            except:  # FIXME: we add try/except here for case
                    # if user object already exists
                manual_create_email_user(user)
                token = user.emailuser.generate_token()
            if settings.DEBUG:
                print "Token - %s" % token

            send_mail(u'Вход на сайт %s' % settings.SITE_URL,
                      (u'\nДля входа на сайт пройдите по ссылке:'
                       u'%s/auth/%s/%s/ \n'
                       u'Если у Вас возникли проблемы со входом '
                       u'напишите письмо на %s' % (settings.SITE_URL,
                                                   user.pk, token,
                                                   settings.SERVER_EMAIL)),
                      settings.SERVER_EMAIL, [email], fail_silently=False)

            sended = True
    else:
        form = EmailUserForm()
    return render(request, "user/login.html", {'form': form, 'sended': sended})


@never_cache
def logout_view(request):
    logout(request)
    return redirect('index_page')
