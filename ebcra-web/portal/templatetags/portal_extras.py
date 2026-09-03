from django import template
from django.template.loader_tags import BLOCK_CONTEXT_KEY
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag(takes_context=True)
def block_content(context, name):
    """Render the most-derived content of the named {% block %} for reuse
    outside it (e.g. mirroring page_title into og:title/twitter:title)."""
    block_context = context.render_context.get(BLOCK_CONTEXT_KEY)
    node = block_context.get_block(name) if block_context else None
    if node is None:
        return ""
    return mark_safe(node.render(context))


@register.filter
def calculate_variation(last, compare):
    """Return formatted % change from compare to last, e.g. '+15.3%' or '-5.2%'."""
    try:
        last = float(last)
        compare = float(compare)
        if compare == 0:
            return "N/A"
        pct = (last - compare) / abs(compare) * 100
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.1f}%"
    except (TypeError, ValueError):
        return "N/A"


@register.filter
def format_integer(value):
    """Format a numeric value as a plain integer (no scientific notation)."""
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return value


@register.filter
def format_date(value):
    """Trim ISO datetime string to date only (e.g. '2026-04-27T00:00:00Z' → '2026-04-27')."""
    try:
        return str(value)[:10]
    except (TypeError, ValueError):
        return value


@register.filter
def format_number(value, lang='es'):
    """Format a numeric value with locale-appropriate thousands/decimal separators."""
    try:
        num = float(value)
        if num == int(num):
            formatted = f"{int(num):,}"
        else:
            formatted = f"{num:,.2f}"
        if lang == 'en':
            return formatted
        return formatted.replace(',', 'X').replace('.', ',').replace('X', '.')
    except (TypeError, ValueError):
        return value
