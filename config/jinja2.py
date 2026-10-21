from django.contrib import messages
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from jinja2 import Environment


def url(name, *args, **kwargs):
    return reverse(name, args=args, kwargs=kwargs)


def localtime(value, fmt="%d %b %Y, %H:%M"):
    if not value:
        return "-"
    return timezone.localtime(value).strftime(fmt)


def environment(**options):
    env = Environment(**options)
    env.globals.update(
        {
            "static": static,
            "url": url,
            "get_messages": messages.get_messages,
        }
    )
    env.filters["localtime"] = localtime
    return env
