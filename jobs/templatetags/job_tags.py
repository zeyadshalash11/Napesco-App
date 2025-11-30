from django import template
from jobs.models import DeliveryTicket

register = template.Library()

@register.filter
def model_name(obj):
    return obj.__class__.__name__