import logging

import httpx
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)

# Maps page key → (es_url, en_url)
_ALTERNATE_URLS = {
    "home":           ("/",                                                                  "/en"),
    "base":           ("/base_monetaria_argentina",                                          "/en/argentina_monetary_base"),
    "base_usd":       ("/base_monetaria_argentina_en_usd",                                   "/en/argentina_monetary_base_in_usd"),
    "base_div_res":   ("/base_monetaria_dividida_reservas_internacionales_argentina",        "/en/argentina_monetary_base_divided_by_international_reserves"),
    "componentes":    ("/componentes_base_monetaria_argentina",                              "/en/argentina_monetary_base_components"),
    "reservas":          ("/reservas_internacionales_argentina",                               "/en/argentina_international_reserves"),
    "comp_reservas":     ("/composicion_reservas_internacionales_argentina",                 "/en/argentina_international_reserves_composition"),
    "fact_var_reservas": ("/factores_variacion_reservas_internacionales_argentina",          "/en/argentina_international_reserves_variation_factors"),
    "depositos":         ("/depositos_argentina",                                            "/en/argentina_deposits"),
    "depositos_sector":  ("/depositos_por_sector_argentina",                                "/en/argentina_deposits_by_sector"),
    "depositos_usd":     ("/depositos_en_dolares_argentina",                                "/en/argentina_usd_deposits"),
    "m1_argentina":   ("/m1",                                                                "/en/argentina_m1"),
    "m1_usd":         ("/m1_en_usd",                                                         "/en/argentina_m1_in_usd"),
    "m1_div_res":     ("/m1_dividido_reservas_internacionales_argentina",                    "/en/argentina_m1_divided_by_international_reserves"),
    "m2_argentina":   ("/m2",                                                                "/en/argentina_m2"),
    "m2_usd":         ("/m2_en_usd",                                                         "/en/argentina_m2_in_usd"),
    "m2_div_res":                   ("/m2_dividido_reservas_internacionales_argentina",    "/en/argentina_m2_divided_by_international_reserves"),
    "m3_argentina":   ("/m3",                                                                "/en/argentina_m3"),
    "m3_usd":         ("/m3_en_usd",                                                         "/en/argentina_m3_in_usd"),
    "m3_div_res":     ("/m3_dividido_reservas_internacionales_argentina",                    "/en/argentina_m3_divided_by_international_reserves"),
    "prestamos":          ("/prestamos_argentina",                                               "/en/argentina_loans"),
    "prestamos_por_tipo": ("/prestamos_por_tipo_argentina",                                      "/en/argentina_loans_by_type"),
    "porc_prestamos": ("/porcentaje_prestamos_vs_depositos_argentina",                       "/en/argentina_percentage_loans_vs_deposits"),
    "tasas":          ("/tasas_de_interes_argentina",                                        "/en/argentina_interest_rates"),
    "tasas_prestamos": ("/tasas_de_interes_de_prestamos_argentina",                          "/en/argentina_lending_interest_rates"),
    "tasas_depositos": ("/tasas_de_interes_de_depositos_argentina",                          "/en/argentina_deposit_interest_rates"),
    "depositos_titular": ("/depositos_por_titular_argentina",                                "/en/argentina_deposits_by_holder"),
    "hipotecarios_prendarios": ("/prestamos_hipotecarios_y_prendarios_argentina",            "/en/argentina_mortgage_and_secured_loans"),
    "prestamos_titular":       ("/prestamos_por_titular_argentina",                          "/en/argentina_loans_by_borrower"),
    "cer":            ("/cer",                                                               "/en/cer"),
    "uva":            ("/unidad_de_valor_adquisitivo",                                       "/en/unit_of_purchasing_value"),
    "uvi":            ("/unidad_de_vivienda",                                                "/en/unit_of_dwelling"),
    "icl":            ("/icl",                                                               "/en/icl"),
    "pases":          ("/pases_argentina",                                                  "/en/argentina_repo_operations"),
    "inf_mensual":    ("/inflacion_mensual_argentina",                                       "/en/argentina_monthly_inflation"),
    "inf_interanual": ("/inflacion_interanual_argentina",                                    "/en/argentina_annual_inflation"),
    "inf_esperada":   ("/inflacion_esperada_argentina",                                      "/en/argentina_expected_inflation"),
    "merval":         ("/indice_merval",                                                     "/en/merval_index"),
    "merval_usd":     ("/merval_en_dolares",                                                 "/en/merval_in_usd"),
    "rentabilidades": ("/rentabilidades",                                                    "/en/argentina_annual_profitability"),
    "sources":        ("/fuentes",                                                           "/en/sources"),
    "credits":        ("/creditos",                                                          "/en/credits"),
    "nota_inflacion": ("/nota_sobre_los_datos_oficiales_de_inflacion",                       "/en/note_on_inflation_data"),
    "liquidez_sistema_financiero": ("/liquidez_sistema_financiero_argentina",                 "/en/argentina_financial_system_liquidity"),
    "interfaz_fiscal_monetaria": ("/interfaz_fiscal_monetaria",                               "/en/fiscal_monetary_interface"),
    "release_notes":  ("/release_notes",                                                     "/release_notes"),
    "error":          ("/error",                                                             "/en/error"),
    "api_info":       ("/api/documentacion",                                                 "/api/documentation"),
}

# Pages excluded from the sitemap (not real content pages).
_SITEMAP_EXCLUDED_PAGES = {"error"}

# Pages that aren't a single BCRA time-series report (landing page, static text,
# error page, API docs) — excluded from the per-page Dataset JSON-LD.
_NON_DATASET_PAGES = {"home", "sources", "credits", "nota_inflacion", "release_notes", "error", "api_info"}

# Category groupings for breadcrumbs, mirroring the sidebar nav in base.html
# (label_es, label_en, [page keys]). Pages not listed here (home, error,
# nota_inflacion — an orphan page not linked from the nav) get no breadcrumb.
_CATEGORIES = [
    ("Reservas Internacionales", "International Reserves",
     ["reservas", "comp_reservas", "fact_var_reservas", "base_div_res", "m1_div_res", "m2_div_res", "m3_div_res"]),
    ("Base Monetaria", "Monetary Base",
     ["base", "base_usd", "componentes"]),
    ("Agregados Monetarios", "Monetary Aggregates",
     ["m1_argentina", "m1_usd", "m2_argentina", "m2_usd", "m3_argentina", "m3_usd"]),
    ("Operaciones de Pase BCRA", "BCRA Repo Operations",
     ["pases", "interfaz_fiscal_monetaria"]),
    ("Depósitos y Préstamos", "Deposits and Loans",
     ["depositos", "depositos_sector", "depositos_usd", "depositos_titular",
      "liquidez_sistema_financiero", "prestamos", "prestamos_por_tipo",
      "hipotecarios_prendarios", "prestamos_titular", "porc_prestamos"]),
    ("Tasas de Interés", "Interest Rates",
     ["tasas", "tasas_prestamos", "tasas_depositos"]),
    ("Inflación", "Inflation",
     ["inf_mensual", "inf_interanual", "inf_esperada"]),
    ("Índices", "Indexes",
     ["cer", "uva", "uvi", "icl"]),
    ("Otros", "Other",
     ["merval", "merval_usd", "rentabilidades"]),
    ("API (Deprecada)", "API (Deprecated)",
     ["api_info"]),
    ("Acerca De", "About",
     ["sources", "credits", "release_notes"]),
]

_PAGE_CATEGORY = {
    page: (label_es, label_en)
    for label_es, label_en, pages in _CATEGORIES
    for page in pages
}

# Pages that require a backend variations API call, mapped to the API path
_VARIATIONS_PATHS = {
    "base":        "/var_base",
    "base_usd":    "/var_base_usd",
    "base_div_res":"/var_base_div_res",
    "componentes": "/var_componentes",
    "reservas":        "/var_res",
    "comp_reservas":   "/var_comp_reservas",
    "depositos":        "/var_depositos_por_tipo",
    "depositos_sector": "/var_depositos_sector",
    "depositos_usd":    "/var_depositos_usd",
    "m1_argentina": "/var_m1",
    "m1_div_res":   "/var_m1_div_res",
    "m2_argentina":"/var_m2",
    "m2_usd":      "/var_m2_usd",
    "m2_div_res":                   "/var_m2_div_res",
    "m3_argentina": "/var_m3",
    "m3_div_res":   "/var_m3_div_res",
    "liquidez_sistema_financiero": "/var_liquidez_sistema_financiero",
    "depositos_titular":       "/var_depositos_titular",
    "hipotecarios_prendarios": "/var_hipotecarios_prendarios",
    "prestamos_titular":       "/var_prestamos_titular",
    "prestamos":               "/var_prestamos",
    "prestamos_por_tipo": "/var_prestamos_por_tipo",
    "pases":       "/var_pases",
    "merval":      "/var_merval",
    "merval_usd":  "/var_merval_div_usd",
}


def _lang(request):
    return "en" if request.path.startswith("/en") else "es"


def _ctx(request, page):
    lang = _lang(request)
    es_url, en_url = _ALTERNATE_URLS.get(page, ("/", "/en"))
    alternate_url = en_url if lang == "es" else es_url
    category = _PAGE_CATEGORY.get(page)
    breadcrumb_category = (category[1] if lang == "en" else category[0]) if category else None
    return {
        "lang": lang,
        "page": page,
        "alternate_url": alternate_url,
        "is_dataset": page not in _NON_DATASET_PAGES,
        "breadcrumb_category": breadcrumb_category,
    }


def _fetch_variations(path):
    host = settings.VARIATIONS_SERVICE_HOST
    if not host:
        return {}
    url = host + path
    try:
        resp = httpx.get(url, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("Variations service returned %s for %s", e.response.status_code, url)
        return {}
    except httpx.RequestError as e:
        logger.error("Variations service call failed for %s: %s", url, e)
        return {}


def _cache_headers(response):
    if not settings.DEBUG:
        response["Cache-Control"] = "max-age=14400, public"
    return response


def home(request):
    ctx = _ctx(request, "home")
    ctx["variations"] = _fetch_variations("/var_base_res")
    response = render(request, "portal/pages/home.html", ctx)
    return _cache_headers(response)


def report(request, page):
    ctx = _ctx(request, page)
    if page in _VARIATIONS_PATHS:
        ctx["variations"] = _fetch_variations(_VARIATIONS_PATHS[page])
    response = render(request, f"portal/pages/{page}.html", ctx)
    return _cache_headers(response)


def error_page(request):
    ctx = _ctx(request, "error")
    ctx["error_code"] = 500
    return render(request, "portal/pages/error.html", ctx, status=500)


def page_not_found(request, exception=None):
    ctx = _ctx(request, "error")
    ctx["error_code"] = 404
    return render(request, "portal/pages/error.html", ctx, status=404)


def robots_txt(request):
    lines = [
        "User-agent: *",
        "Allow: /",
        "",
        f"Sitemap: {settings.SITE_URL}/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


def sitemap_xml(request):
    seen = set()
    urls = []
    for page, (es_url, en_url) in _ALTERNATE_URLS.items():
        if page in _SITEMAP_EXCLUDED_PAGES:
            continue
        for url in (es_url, en_url):
            if url not in seen:
                seen.add(url)
                urls.append(url)
    urls.sort()
    response = render(request, "portal/sitemap.xml", {"urls": urls}, content_type="application/xml")
    return _cache_headers(response)


def api_info(request):
    lang = "en" if request.path.endswith("/documentation") else "es"
    es_url, en_url = _ALTERNATE_URLS["api_info"]
    label_es, label_en = _PAGE_CATEGORY["api_info"]
    ctx = {
        "lang": lang,
        "page": "api_info",
        "alternate_url": en_url if lang == "es" else es_url,
        "is_dataset": False,
        "breadcrumb_category": label_en if lang == "en" else label_es,
    }
    response = render(request, "portal/pages/api_info.html", ctx)
    return _cache_headers(response)
