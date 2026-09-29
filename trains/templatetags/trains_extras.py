from django import template

register = template.Library()


@register.filter
def yesnojs(value):
    return "true" if value else "false"
