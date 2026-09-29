from django.template import Library, Node
from django.conf import settings
from datetime import datetime

from flash.models import *

register = Library()

def build_random_flashses(parser, token):
    """
    {% get_random_flashses %}
    """
    return RandomFlashesObject()

class RandomFlashesObject(Node):
    def render(self, context):
        flash_list = Flash.objects.filter(active=True, publication_date__lt=datetime.now()).order_by("?")[:settings.RANDOM_FLASH_COUNT]
        context['random_flash_list'] = flash_list
        print flash_list
        return ''

register.tag('get_random_flashses', build_random_flashses)



def build_best_flashses(parser, token):
    """
    {% get_best_flashses %}
    """
    return BestFlashesObject()

class BestFlashesObject(Node):
    def render(self, context):
        flash_list = Flash.objects.filter(active=True, publication_date__gt=datetime.now()).order_by("-xrate")[:settings.BEST_FLASH_COUNT]
        context['best_flash_list'] = flash_list
        return ''

register.tag('get_best_flashses', build_best_flashses)


def get_themes(parser, token):
    """
    {% get_themes %}
    """
    return ThemesObject()

class ThemesObject(Node):
    def render(self, context):
        theme_list = Theme.objects.filter(count__gt=0).order_by("name")
        context['theme_list'] = theme_list
        return ''

register.tag('get_themes', get_themes)

