from django import template
import time
import os

register = template.Library()

@register.simple_tag
def version_date():
    return f"0.{time.strftime('%m%d', time.gmtime(os.path.getmtime('./version')))}"
