# inventory/templatetags/inventory_extras.py

from django import template
from django.utils.safestring import mark_safe
import re

register = template.Library()

@register.filter
def highlight(text, query):
    """
    Highlights all occurrences of the query in the text.
    """
    if not query:
        return text

    # Use re.escape to safely handle special characters in the query
    # and re.IGNORECASE for a case-insensitive match
    highlighted = re.sub(
        f'({re.escape(query)})', 
        r'<mark>\1</mark>', 
        text, 
        flags=re.IGNORECASE
    )
    
    return mark_safe(highlighted)