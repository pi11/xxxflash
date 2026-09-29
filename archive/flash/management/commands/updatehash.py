from flash.models import *
from django.core.management.base import BaseCommand, CommandError
from local_settings import MEDIA_ROOT
import hashlib

class Command(BaseCommand):
    args = ''
    help = 'Update datahash'     

    def handle(self, *args, **options):
        i=0
        for flash in Flash.objects.all():
            i+=1
            f = open(MEDIA_ROOT+str(flash.flashfile))
            data=f.read()
            f.close()
            m=hashlib.new("sha512")
            m2=hashlib.new("sha512")
            l=len(data)
            print "Data len=", l
            m.update(data[:l])
            m2.update(data[l:])
            dh1 = m.hexdigest()
            dh2 = m2.hexdigest()
            dh=str(dh1)+str(dh2)
            flash.datahash=dh
            flash.save()
            print "%s updated" %i


            


