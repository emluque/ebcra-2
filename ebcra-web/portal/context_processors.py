from django.conf import settings


def site_globals(request):
    return {
        "GOOGLE_ANALYTICS_ID": settings.GOOGLE_ANALYTICS_ID,
        "SITE_URL": settings.SITE_URL,
        "jsToken": getattr(request, "js_token", ""),
        "CHART_API_BASE_URL": f"{settings.CHART_API_SCHEME}://{settings.CHART_API_HOST}",
    }
