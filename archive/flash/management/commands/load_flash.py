# -*- coding: utf-8 -*-

from flash.models import *
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
import random
import hashlib
import os
import shutil


def get_hash(filename):
    """

    """
    f = open(filename)
    data = f.read()
    f.close()
    m = hashlib.new("sha512")
    m2 = hashlib.new("sha512")
    l = len(data)
    print "Data len=", l
    m.update(data[:l])
    m2.update(data[l:])  # тут полная хуйня происходит, всегда data[l:] === ''
    dh1 = m.hexdigest()
    dh2 = m2.hexdigest()
    dh = "%s%s" % (dh1, dh2)
    return dh


class Command(BaseCommand):
    args = ''
    help = 'Load flash games'

    def add_arguments(self, parser):
        parser.add_argument('source_path', help='source path with swf files')
        parser.add_argument('default_theme',
                            help='default theme for new swf files',
                            default='erotic')
        parser.add_argument('--show_themes', action='store_true',
                            default=False, dest='show_themes')

    def handle(self, *args, **options):
        if options['show_themes']:
            for t in Theme.objects.all():
                print t.url
            return
        print options

        user = User.objects.get(username='Anonymous')
        full_path = options['source_path']  # 'media/flashsex.ru/flashgames/'
        print options['default_theme']
        theme_url = options['default_theme']  # 'Erotic'
        theme = Theme.objects.get(url=theme_url)
        restored, new = 0, 0
        for root, dirs, files in os.walk(full_path):
            for filename in files:
                full_name = os.path.join(root, filename)
                print "SOURSE: %s" % full_name
                name, ext = os.path.splitext(filename)
                if ext.lower() == '.swf':
                    name = u"Игра без названия"
                    text = u"Описания для этой порно игры пока нет."
                    fhash = get_hash(full_name)
                    try:
                        flash_c = Flash.objects.get(datahash=fhash)
                    except Flash.DoesNotExist:
                        print "New game."
                        new += 1
                        print "New flash - %s" % full_name
                        k = random.randint(100, 1000000)
                        dst_file = "%sswf/all/game-%s.swf" % (
                            settings.MEDIA_ROOT, k)
                        print dst_file
                        # flashfile = "flashgames/%s.swf" % i
                        while os.path.exists(dst_file):
                            k = random.randint(100, 1000000)
                            dst_file = "%sswf/all/game-%s.swf" % (
                                settings.MEDIA_ROOT, k)
                        print "Copying file from %s to %s" % (full_name,
                                                              dst_file)
                        shutil.copyfile(full_name, dst_file)
                        mroot = settings.MEDIA_ROOT.replace("//", "/")
                        tt = Flash(name=name, description=text, user=user,
                                   flashfile=dst_file.replace(mroot, ''),
                                   datahash=fhash, active=False)
                        tt.save()
                        tt.theme.add(theme)

                    else:
                        print "Old game"
                        if flash_c.is_flash_exist():
                            print "File is OK, skipping..."
                        else:
                            print "File is deleted, lets restore it"
                            print flash_c.flashfile.path
                            dir_p = os.path.split(flash_c.flashfile.path)[0]
                            try:
                                os.makedirs(dir_p)
                            except OSError:
                                pass
                            shutil.copyfile(full_name, flash_c.flashfile.path)
                            restored += 1

        print "Total restored: %s, total new files: %s" % (restored, new)
