from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path
from django.views.generic import RedirectView

from portal import views as portal_views

handler404 = portal_views.page_not_found
handler500 = portal_views.error_page

urlpatterns = [
    path("", include("portal.urls_es")),
    path("en/", include("portal.urls_en")),
    path("api/documentacion", portal_views.api_info, name="api_info_es"),
    path("api/documentation", portal_views.api_info, name="api_info_en"),
    path("api/registracion", RedirectView.as_view(url="/api/documentacion", permanent=True)),
    path("api/registration", RedirectView.as_view(url="/api/documentation", permanent=True)),
]

urlpatterns += staticfiles_urlpatterns()
