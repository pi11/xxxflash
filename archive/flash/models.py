# -*- coding: utf-8 -*-
import os.path
import hashlib
from random import randint
from datetime import datetime
from PIL import Image

from django.db import models
from django.contrib.auth.models import User
from django.forms import ModelForm
from django import forms
from django.db.models import signals
from django.core.exceptions import ValidationError
from django.conf import settings
from djangosphinx.models import SphinxSearch
from djangohelpers.images import scale
from django.utils import timezone

from flash.signals import create_profile

signals.post_save.connect(create_profile, sender=User)


class SimpleURLField(models.URLField):

    def pre_save(self, model_instance, add):
        url = getattr(model_instance, self.attname, '')
        if add and url and not url.startswith('http://'):
            url = 'http://%s' % url
            setattr(model_instance, self.attname, url)
            return url
        return models.URLField.pre_save(self, model_instance, add)


class Theme(models.Model):

    """Theme model"""

    name = models.CharField(max_length=250)
    url = models.CharField(max_length=100)
    active = models.BooleanField()
    publication_date = models.DateField(default=timezone.now)
    count = models.IntegerField(default=0)
    order = models.IntegerField(default=0)

    def __unicode__(self):
        return self.name

    @models.permalink
    def get_absolute_url(self):
        return ("theme", [self.url])

    class Meta:
        ordering = ["-order", "name"]

    class Admin:
        list_display = ('name', 'active', 'publication_date',)
        list_filter = ('name', 'publication_date',)
        ordering = ('name', 'publication_date', )


class Screenshot(models.Model):
    flash = models.ForeignKey('Flash')
    image = models.ImageField(
        upload_to='screenshots/%Y/%m/%d', max_length=150)  # preview file

    def __unicode__(self):
        return unicode(self.pk)

    def get_thumb(self):
        try:
            thumb = scale(self.image, "%sx%s" % (settings.SMALL_THUMB_WIDTH,
                                                 settings.SMALL_THUMB_HEIGHT))
        except:
            import traceback
            print traceback.format_exc()
            thumb = False
        return thumb

    class Meta:
        ordering = ["flash", ]

    class Admin:
        list_display = ('image', 'flash',)
        list_filter = ('flash', 'image',)
        ordering = ('flash', )


class Flash(models.Model):

    """
    Flash models. Do not forget to set SPHINX_INDEX value
    """

    GAME_TYPE = (
        (0, 'Flash'),
        (1, 'Downloadable'),
    )
    search = SphinxSearch(index=settings.SPHINX_INDEX)

    name = models.CharField(max_length=150)
    description = models.TextField(max_length=2000)
    theme = models.ManyToManyField(Theme)
    game_type = models.IntegerField(choices=GAME_TYPE, default=0)
    user = models.ForeignKey(User)
    flashfile = models.FileField(upload_to='swf/%Y/%m/%d', max_length=150)
    thumbfile = models.ImageField(
        upload_to='th/%Y/%m/', blank=True)  # preview file
    filesize = models.CharField(max_length=20, default="0")
    rate = models.IntegerField(default=0)
    views = models.IntegerField(default=0)
    active = models.BooleanField(default=True)
    publication_date = models.DateField(default=timezone.now)
    datahash = models.CharField(max_length=512, unique=True)
    is_posted = models.BooleanField(default=False)
    width = models.IntegerField(default=0)
    height = models.IntegerField(default=0)

    xrate = models.FloatField(default=0)  # new rate value

    def is_flash_exist(self):
        if os.path.exists(self.flashfile.path):
            return True
        else:
            return False

    def get_screenshots(self):
        screens = Screenshot.objects.filter(flash=self)
        return screens

    def gthumb(self):
        return "<img src='%s%s' width='50px' />" % (settings.MEDIA_URL, self.thumbfile)

    gthumb.allow_tags = True

    def get_preview(self):
        pr = """
        <a style="cursor:pointer;" onclick="django.jQuery('#pr-%s').toggle()">Toggle View</a>
        <div id="pr-%s" style="display:none;">
        <object type="application/x-shockwave-flash" style="width:450px; height:450px;" data="%s%s"><param name="movie" value="%s%s" />
	</object>
        </div>
        """ % (self.pk, self.pk, settings.MEDIA_URL,
               self.flashfile, settings.MEDIA_URL,
               self.flashfile)
        return pr

    get_preview.allow_tags = True

    def save(self, *args, **kwargs):
        if self.id is None:
            new = True
            self.user = User.objects.filter(username='Anonymous')[0]
        else:
            new = False

        if self.width == 0 or self.width is None and new == False:
            try:
                import hexagonit.swfheader
            except ImportError:
                pass
            else:
                try:
                    self.flashfile.open()
                except (ValueError, IOError):
                    pass
                else:
                    try:
                        metadata = hexagonit.swfheader.parse(self.flashfile)
                    except:
                        pass
                    else:
                        self.width, self.height = metadata[
                            'width'], metadata['height']
                        self.size = metadata['size']
                    finally:
                        self.flashfile.close()

        super(Flash, self).save(*args, **kwargs)
        if new:
            if self.thumbfile and os.path.exists(self.thumbfile.path):
                image = Image.open(self.thumbfile.path)
                if image.mode != "RGB":
                    image = image.convert("RGB")
                image = image.resize((350, 350), Image.ANTIALIAS)
                image.save(self.thumbfile.path)

    def get_thumb(self):
        try:
            thumb = scale(self.thumbfile, "%sx%s" % (settings.THUMB_WIDTH,
                                                     settings.THUMB_HEIGHT))
        except:
            import traceback
            print traceback.format_exc()
            thumb = False
        return thumb

    def __unicode__(self):
        return self.name

    @models.permalink
    def get_absolute_url(self):
        return ("view_game", [self.id])

    @property
    def get_width(self):
        return settings.DEFAULT_WIDTH

    @property
    def get_height(self):
        try:
            h = float(self.height)
        except:
            h = settings.DEFAULT_WIDTH
        ratio = float(self.width) // h
        try:
            h = int(h)
        except:
            h = settings.DEFAULT_WIDTH
        if h < 1:
            h = settings.DEFAULT_WIDTH
        return h

    def clean(self):
        f = self.flashfile
        try:
            data = f.read()
            f.close()
        except IOError:
            print "Flash file not found..."
            pass
        else:
            m = hashlib.new("sha512")
            m2 = hashlib.new("sha512")
            l = len(data)
            m.update(data[:l])
            m2.update(data[l:])
            dh1 = m.hexdigest()
            dh2 = m2.hexdigest()
            dh = "%s%s" % (dh1, dh2)
            self.datahash = dh
            try:
                f = Flash.objects.get(datahash=dh)
            except Flash.DoesNotExist:
                pass
            else:
                if f != self:
                    raise ValidationError('This game already loaded')

    class Meta:
        ordering = ["name", ]

    class Admin:
        list_display = ('name', 'theme', 'game_type', 'flashfile',
                        'user', 'rate', 'views', 'game_type',  'publication_date',)
        list_filter = ('name', 'theme', 'user',
                       'rate', 'views',  'publication_date',)
        ordering = ('name', 'publication_date', )

# class FlashForm(forms.Form):
#    name = forms.CharField(max_length=150)
#    theme = forms.ModelMultipleChoiceField(queryset=Theme.objects.filter(pk__gt=0) )
#    wallfile = forms.ImageField()


class Mark(models.Model):
    flash = models.ForeignKey(Flash)
    mark = models.IntegerField()

    def __unicode__(self):
        return str(self.mark)

    class Meta:
        ordering = ["flash", ]

    class Admin:
        list_display = ('mark', 'flash',)
        list_filter = ('flash', 'mark',)
        ordering = ('flash', )


class CMark(models.Model):
    flash = models.ForeignKey(Flash)
    ip = models.GenericIPAddressField()
    mark = models.IntegerField()
    publication_date = models.DateField(default=timezone.now)

    def __unicode__(self):
        return str(self.ip)

    class Meta:
        ordering = ["ip", ]

    class Admin:
        list_display = ('ip', 'flash', 'mark', 'publication_date',)
        list_filter = ('ip', 'flash', 'mark', 'publication_date',)
        ordering = ('publication_date', 'ip', )


class Ban(models.Model):
    ip = models.GenericIPAddressField()
    publication_date = models.DateField(default=timezone.now)

    def __unicode__(self):
        return str(self.ip)

    class Meta:
        ordering = ["ip", ]


class Comment(models.Model):
    flash = models.ForeignKey(Flash)
    user = models.ForeignKey(User)
    text = models.TextField(max_length=1000)
    ip = models.CharField(max_length=40, blank=True, null=True)
    ua = models.CharField(max_length=250, blank=True, null=True)
    publication_date = models.DateField(default=timezone.now)

    def __unicode__(self):
        return self.text

    class Meta:
        ordering = ["publication_date"]

    class Admin:
        list_display = ('publication_date', 'flash', 'user', )
        list_filter = ('publication_date', 'user', 'flash')
        ordering = ('-publication_date', )


class CommentForm(forms.Form):
    text = forms.CharField(widget=forms.Textarea, required=True)
    flash_id = forms.DecimalField()

    def clean_text(self):
        t = self.cleaned_data['text']
        if u"апиши этот коммент" in t:
            raise ValidationError("Негодный коммент")
        return t


class MyFlash(models.Model):
    flash = models.ForeignKey(Flash)
    text = models.TextField(max_length=200)
    user = models.ForeignKey(User)

    def __unicode__(self):
        return self.flash.name

    class Meta:
        ordering = ["flash", "text", ]

    class Admin:
        list_display = ('flash', 'user', 'text', )
        list_filter = ('text', 'user', 'flash',)
        ordering = ('flash', 'user', 'text', )


class FlashForm(forms.Form):
    name = forms.CharField(max_length=150)
    theme = forms.ModelMultipleChoiceField(
        queryset=Theme.objects.filter(pk__gt=0))
    # tagslist = forms.CharField(max_length=250)
    description = forms.CharField(widget=forms.Textarea, max_length=2000)
    flashfile = forms.FileField()
    thumbfile = forms.ImageField()

    def clean_flashfile(self):
        flashfile = self.cleaned_data['flashfile']
        content_type = flashfile.content_type.split('/')[1]
        if content_type not in settings.CONTENT_TYPES:
            raise forms.ValidationError('Неверный тип файла')
        return flashfile


class Profile(models.Model):
    # GENDER_CHOICES = (
    #(1, 'Male'),
    #(2, 'Female'),
    #)

    user = models.OneToOneField(User)
    # gender = models.PositiveSmallIntegerField(('gender'),
    # choices=GENDER_CHOICES, blank=True, null=True)
    score = models.IntegerField(default=0, editable=False)
    avatar = models.ImageField(upload_to='avatars/%Y/%m/', blank=True)
    site = SimpleURLField(max_length=50, blank=True)
    about = models.TextField(max_length=250, blank=True)

    def save(self, *args, **kwargs):

        super(Profile, self).save(*args, **kwargs)

        if self.id is not None:
            previous = Profile.objects.get(id=self.id)
            if self.avatar and os.path.exists(self.avatar.path):
                try:
                    image = Image.open(self.avatar.path)
                    image = image.resize((150, 150), Image.ANTIALIAS)
                    image.save(self.avatar.path)
                except:
                    pass

    def __unicode__(self):
        return self.user.username

    class Meta:
        ordering = ["user", "score", ]

    class Admin:
        list_display = ('user', 'score', 'avatar', )
        list_filter = ('user', 'score', 'avatar', 'site', 'about',)
        ordering = ('user', 'score', )

    def get_absolute_url(self):
        return ('profiles_profile_detail', (), {'username': self.user.username})
    get_absolute_url = models.permalink(get_absolute_url)


class BannedWord(models.Model):
    word = models.CharField(max_length=100, unique=True)
    publication_date = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return self.word


class Search(models.Model):
    query = models.CharField(max_length=500)
    count = models.IntegerField(default=0)

    def __unicode__(self):
        return self.query
