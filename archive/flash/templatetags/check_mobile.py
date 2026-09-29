from django.template import Library, Node, Variable
from django.utils.safestring import mark_safe

from djangohelpers import edge

register = Library()

def is_edge(parser, token):
    """
    {% is_edge %}
    """
    return EdgeObject()

class EdgeObject(Node):

    def __init__(self,):
        self.request = Variable('request')
        pass
    
    def render(self, context):
        rqst = self.request.resolve(context)
        context['is_edge'] = edge.is_mobile(rqst)
        return ''

register.tag('check_mobile', is_edge)
