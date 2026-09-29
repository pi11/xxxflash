from flash.models import *
from django.core.management.base import BaseCommand, CommandError
from local_settings import SITE_URL
import twit

class Command(BaseCommand):
    args = ''
    help = 'Post wallpaper to twitter'     

    def handle(self, *args, **options):
        ww=Flash.objects.filter(is_posted=False).order_by("publication_date")[:10]
        for w in ww:
            twit.post_twit("New image: "+SITE_URL+"game/"+str(w.id)+"/ #games #flash #fun. More at "+SITE_URL)
            w.is_posted=True
            w.save()
            

            


