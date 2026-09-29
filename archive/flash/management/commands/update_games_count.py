# -*- coding: utf-8 -*-

from flash.models import Theme, Flash
from django.core.management.base import BaseCommand, CommandError

from datetime import datetime

class Command(BaseCommand):
    args = ''
    help = 'update games count'     


    def handle(self, *args, **options):
        for t in Theme.objects.all():
            t.count = Flash.objects.filter(theme=t, publication_date__lt=datetime.now(),
                                           active=True).count()
            t.save()

