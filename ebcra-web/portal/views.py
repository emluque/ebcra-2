import logging

import httpx
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.html import format_html

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
    "status":         ("/estado",                                                            "/en/status"),
    "nota_inflacion": ("/nota_sobre_los_datos_oficiales_de_inflacion",                       "/en/note_on_inflation_data"),
    "liquidez_sistema_financiero": ("/liquidez_sistema_financiero_argentina",                 "/en/argentina_financial_system_liquidity"),
    "interfaz_fiscal_monetaria": ("/interfaz_fiscal_monetaria",                               "/en/fiscal_monetary_interface"),
    "release_notes":  ("/release_notes",                                                     "/release_notes"),
    "error":          ("/error",                                                             "/en/error"),
    "api_info":       ("/api/documentacion",                                                 "/api/documentation"),
}

# Pages excluded from the sitemap (not real content pages).
_SITEMAP_EXCLUDED_PAGES = {"error", "status"}

# Pages that aren't a single BCRA time-series report (landing page, static text,
# error page, API docs) — excluded from the per-page Dataset JSON-LD.
_NON_DATASET_PAGES = {"home", "sources", "credits", "status", "nota_inflacion", "release_notes", "error", "api_info"}

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
     ["sources", "credits", "status", "release_notes"]),
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

# Data-freshness threshold, must match ebcra-scrapping/scraper/db.py::STALE_THRESHOLD_DAYS
_STALE_THRESHOLD_DAYS = 31

# Human-readable labels for the actively-scraped web sources, used when a
# calculated table's degradation traces back to one of them rather than to a
# BCRA API variable.
_SOURCE_LABELS = {
    "dollar_blue_cronista": "Dollar Blue",
    "dollar_blue_unified": "Dollar Blue",
    "merval_yahoo": "Merval",
    "merval_unified": "Merval",
}

# Human-readable names per BCRA-variable table, so a warning can name exactly
# which series is affected instead of just saying "this variable" — needed on
# reports that plot several BCRA variables in one chart (e.g. depositos_sector).
# Pulled directly from each chart's own series `name:` field in the page
# templates (the same label already shown in the chart legend/tooltip), so it
# stays in sync with what the site actually calls each series.
_TABLE_LABELS = {
    "bcra_adelantos_transitorios_imd": {"es": "Adelantos Transitorios", "en": "Temporary Advances"},
    "bcra_asignaciones_deg_2009": {"es": "Asignaciones DEG 2009", "en": "SDR Allocations 2009"},
    "bcra_base_monetaria": {"es": "Base Monetaria", "en": "Monetary Base"},
    "bcra_billetes_y_monedas_publico": {"es": "Billetes y Monedas", "en": "Bills and Coins"},
    "bcra_cer": {"es": "CER", "en": "CER"},
    "bcra_circulacion_monetaria": {"es": "Circulación Monetaria", "en": "Monetary Circulation"},
    "bcra_creditos_sistema_financiero": {"es": "Créditos BCRA", "en": "BCRA Credits"},
    "bcra_dep_titular_ca_privado": {"es": "Cajas de Ahorro", "en": "Savings Accounts"},
    "bcra_dep_titular_cc_privado": {"es": "Cuentas Corrientes", "en": "Checking Accounts"},
    "bcra_dep_titular_fci": {"es": "Fondos Comunes", "en": "Mutual Funds (FCIs)"},
    "bcra_dep_titular_humanas": {"es": "Personas Humanas", "en": "Individuals"},
    "bcra_dep_titular_juridicas": {"es": "Personas Jurídicas", "en": "Companies"},
    "bcra_dep_titular_pf_privado": {"es": "Plazos Fijos", "en": "Time Deposits"},
    "bcra_dep_titular_privado_total": {"es": "Total", "en": "Total"},
    "bcra_dep_titular_pymes": {"es": "PyMEs", "en": "SMEs"},
    "bcra_depositos_a_plazo": {"es": "Plazo Fijo", "en": "Time Deposits"},
    "bcra_depositos_bancos_en_cuenta_corriente_del_bcra": {"es": "Depósitos de Bancos", "en": "Bank Deposits"},
    "bcra_depositos_cajas_ahorro": {"es": "Cajas de Ahorro", "en": "Savings Accounts"},
    "bcra_depositos_cuentas_corrientes": {"es": "Cuentas Corrientes", "en": "Checking Accounts"},
    "bcra_depositos_efectivo_entidades_financieras_total": {"es": "Depósitos Totales", "en": "Total Deposits"},
    "bcra_depositos_gobierno_pesos": {"es": "Depósitos Gobierno (Pesos)", "en": "Government Deposits (Pesos)"},
    "bcra_depositos_gobierno_usd": {"es": "Depósitos Gobierno (USD)", "en": "Government Deposits (USD)"},
    "bcra_depositos_plazo_privado": {"es": "Plazo Privado", "en": "Private Plazo"},
    "bcra_depositos_plazo_publico": {"es": "Plazo Público", "en": "Public Plazo"},
    "bcra_depositos_publico": {"es": "Público Total", "en": "Public Total"},
    "bcra_depositos_usd_efectivo": {"es": "Depósitos de Efectivo", "en": "Cash Deposits"},
    "bcra_depositos_usd_total": {"es": "Depósitos Totales", "en": "Total Deposits"},
    "bcra_depositos_vista_privado": {"es": "Vista Privado", "en": "Private Vista"},
    "bcra_depositos_vista_publico": {"es": "Vista Público", "en": "Public Vista"},
    "bcra_divisas_pase_pasivo_exterior": {"es": "Pase Pasivo con el Exterior", "en": "FX Swap Liability"},
    "bcra_efectivo_en_entidades_financieras": {"es": "Efectivo en Ent. Fin.", "en": "Cash at Fin. Inst."},
    "bcra_hip_construccion": {"es": "Construcción", "en": "Construction"},
    "bcra_hip_nueva": {"es": "Viviendas Nuevas", "en": "New Home"},
    "bcra_hip_otros": {"es": "Otros", "en": "Other"},
    "bcra_hip_refaccion": {"es": "Refacción", "en": "Renovation"},
    "bcra_hip_usada": {"es": "Viviendas Usadas", "en": "Used Home"},
    "bcra_icl": {"es": "ICL", "en": "ICL"},
    "bcra_inflacion_esperada": {"es": "Inf. Esperada", "en": "Expected Inflation"},
    "bcra_inflacion_interanual": {"es": "Inflación Interanual (Oficial)", "en": "Annual Inflation (Official)"},
    "bcra_inflacion_mensual": {"es": "Inf. Mensual (Of.)", "en": "Monthly Inflation (Official)"},
    "bcra_leliq_notaliq": {"es": "Leliq y Notaliq", "en": "Leliq and Notaliq"},
    "bcra_liquidez_pesos": {"es": "Liquidez en Pesos", "en": "Peso Liquidity"},
    "bcra_liquidez_total": {"es": "Liquidez Total", "en": "Total Liquidity"},
    "bcra_m1": {"es": "M1", "en": "M1"},
    "bcra_m2": {"es": "M2", "en": "M2"},
    "bcra_m2_privado": {"es": "M2 Privado", "en": "Private M2"},
    "bcra_m2_transaccional_privado": {"es": "M2 Transaccional Privado", "en": "M2 Transactional Private"},
    "bcra_m3": {"es": "M3", "en": "M3"},
    "bcra_oro_divisas_colocaciones_plazo": {"es": "Activos Brutos de Reserva", "en": "Gross Reserve Assets"},
    "bcra_pases_activos_bcra_saldo": {"es": "Pases Activos BCRA", "en": "BCRA Active Repo"},
    "bcra_pases_pasivos_bcra_fci_saldo": {"es": "Pases Pasivos BCRA (FCI)", "en": "BCRA Passive Repo (FCI)"},
    "bcra_pases_pasivos_bcra_saldo": {"es": "Pases Pasivos BCRA", "en": "BCRA Passive Repo"},
    "bcra_pases_terceros_1_dia_monto": {"es": "Monto Pases Terceros", "en": "Interbank Repo Volume"},
    "bcra_prend_autos": {"es": "Automotores", "en": "Auto Loans"},
    "bcra_prend_maquinarias": {"es": "Maquinarias", "en": "Machinery"},
    "bcra_prend_otros": {"es": "Otros", "en": "Other"},
    "bcra_prest_titular_hipotecarios": {"es": "Hipotecarios", "en": "Mortgage Loans"},
    "bcra_prest_titular_humanas": {"es": "Personas Humanas", "en": "Individuals"},
    "bcra_prest_titular_juridicas": {"es": "Personas Jurídicas", "en": "Companies"},
    "bcra_prest_titular_prendarios": {"es": "Prendarios", "en": "Secured Loans"},
    "bcra_prest_titular_privado_total": {"es": "Total", "en": "Total"},
    "bcra_prest_titular_pymes": {"es": "PyMEs", "en": "SMEs"},
    "bcra_prestamos_adelantos_documentos": {"es": "Adelantos y Documentos", "en": "Advances & Discounts"},
    "bcra_prestamos_entidades_financieras_sector_privado": {"es": "Préstamos", "en": "Loans"},
    "bcra_prestamos_hipotecarios_prendarios": {"es": "Hipotecarios y Prendarios", "en": "Mortgage & Pledge"},
    "bcra_prestamos_otros": {"es": "Otros Préstamos", "en": "Other Loans"},
    "bcra_prestamos_personales_tarjetas": {"es": "Personales y Tarjetas", "en": "Personal & Credit Cards"},
    "bcra_reservas_compra_divisas": {"es": "Compra de Divisas", "en": "FX Purchases"},
    "bcra_reservas_efectivo_minimo": {"es": "Efectivo Mínimo", "en": "Minimum Reserve Req."},
    "bcra_reservas_excluidas_deg_2009": {"es": "Reservas Excl. DEG", "en": "Reserves Excl. SDR"},
    "bcra_reservas_internacionales": {"es": "Reservas Internacionales", "en": "International Reserves"},
    "bcra_reservas_organismos_internacionales": {"es": "Organismos Internacionales", "en": "Intl. Organizations"},
    "bcra_reservas_otras_operaciones": {"es": "Otras Operaciones", "en": "Other Operations"},
    "bcra_reservas_sector_publico": {"es": "Sector Público", "en": "Public Sector"},
    "bcra_tasa_adelantos_cuenta_corriente": {"es": "Tasa Adelantos en Cuenta Corriente", "en": "Overdraft Interest Rate"},
    "bcra_tasa_badlar": {"es": "Badlar", "en": "Badlar"},
    "bcra_tasa_badlar_publicos_y_privados": {"es": "Badlar Pub. y Priv.", "en": "Badlar Pub. & Priv."},
    "bcra_tasa_baibar": {"es": "Baibar", "en": "Baibar"},
    "bcra_tasa_dep_caja_ahorro_a": {"es": "Caja de Ahorro", "en": "Savings Rate"},
    "bcra_tasa_dep_pf_60mas_a": {"es": "60 días o más", "en": "60+ Days"},
    "bcra_tasa_dep_pf_7_59d_a": {"es": "7 a 59 días", "en": "7–59 Days"},
    "bcra_tasa_depositos_30_dias": {"es": "Tasa Depósitos 30 días", "en": "30-day Deposit Rate"},
    "bcra_tasa_depositos_plazo_fijo_usd": {"es": "Total", "en": "All Clients"},
    "bcra_tasa_depositos_plazo_fijo_usd_humanas": {"es": "Personas Humanas", "en": "Individuals"},
    "bcra_tasa_depositos_plazo_fijo_usd_juridicas": {"es": "Personas Jurídicas", "en": "Legal Entities"},
    "bcra_tasa_documentos_sola_firma": {"es": "Documentos a Sola Firma", "en": "Single-Signature Doc."},
    "bcra_tasa_hipotecarios_fija": {"es": "Tasa Hipotecarios (fija)", "en": "Mortgage Rate (fixed)"},
    "bcra_tasa_hipotecarios_uva": {"es": "Tasa Hipotecarios UVA", "en": "Mortgage Rate (UVA)"},
    "bcra_tasa_pase_activas_1_dia": {"es": "T. Pase Activas 1 día", "en": "Active Repo 1d"},
    "bcra_tasa_pase_pasivas_1_dia": {"es": "T. Pase Pasivas 1 día", "en": "Passive Repo 1d"},
    "bcra_tasa_pases_terceros_1_dia": {"es": "Tasa Pases Terceros", "en": "Interbank Repo Rate"},
    "bcra_tasa_prendarios_fija": {"es": "Tasa Prendarios", "en": "Auto/Equipment Loan Rate"},
    "bcra_tasa_prestamos_personales": {"es": "Tasa Préstamos Personales", "en": "Personal Loan Rate"},
    "bcra_tasa_tamar_privados": {"es": "TAMAR Privados", "en": "TAMAR Private"},
    "bcra_tasa_tamar_publicos_y_privados": {"es": "TAMAR Pub. y Priv.", "en": "TAMAR Pub. & Priv."},
    "bcra_tasa_tarjetas_credito": {"es": "Tasa Tarjetas de Crédito", "en": "Credit Card Rate"},
    "bcra_tasa_tm20": {"es": "TM20", "en": "TM20"},
    "bcra_usd_mayorista": {"es": "USD Oficial", "en": "Official USD"},
    "bcra_uva": {"es": "UVA", "en": "UVA"},
    "bcra_uvi": {"es": "UVI", "en": "UVI"},
}

# Pages whose templates carry at least one {% data_warning %} tag (see
# portal/templatetags/portal_extras.py) — each report block names its own
# table_name(s) inline, right above its <div class="subtitle">, so this set
# only gates whether it's worth fetching scrape_status at all for a page.
_CHART_PAGES = {
    "base", "base_div_res", "base_usd", "cer", "comp_reservas", "componentes",
    "depositos", "depositos_sector", "depositos_titular", "depositos_usd",
    "fact_var_reservas", "hipotecarios_prendarios", "home", "icl", "inf_esperada",
    "inf_interanual", "inf_mensual", "interfaz_fiscal_monetaria",
    "liquidez_sistema_financiero", "m1_argentina", "m1_div_res", "m1_usd",
    "m2_argentina", "m2_div_res", "m2_usd", "m3_argentina", "m3_div_res",
    "m3_usd", "merval", "merval_usd", "pases", "porc_prestamos", "prestamos",
    "prestamos_por_tipo", "prestamos_titular", "rentabilidades", "reservas",
    "tasas", "tasas_depositos", "tasas_prestamos", "uva", "uvi",
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


def _fetch_scrape_status():
    host = settings.VARIATIONS_SERVICE_HOST
    if not host:
        return []
    url = host + "/scrape_status"
    try:
        resp = httpx.get(url, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("Scrape status service returned %s for %s", e.response.status_code, url)
        return []
    except httpx.RequestError as e:
        logger.error("Scrape status service call failed for %s: %s", url, e)
        return []


def _root_causes(table_name, statuses, seen=None):
    """Resolve a degraded table to its root cause(s), as ("variable", id, table_name)
    or ("source", label, None) tuples, recursing through nested calculated
    tables via their caused_by list."""
    if seen is None:
        seen = set()
    if table_name in seen:
        return []
    seen.add(table_name)

    row = statuses.get(table_name)
    if not row:
        return []
    kind = row.get("source_kind")

    if kind == "bcra_variable":
        variable_id = row.get("variable_id")
        return [("variable", variable_id, table_name)] if variable_id is not None else []

    if kind in ("cronista", "yahoo"):
        return [("source", _SOURCE_LABELS.get(table_name, table_name), None)]

    if kind == "calculated":
        caused_by = row.get("caused_by") or []
        if not caused_by:
            label = _SOURCE_LABELS.get(table_name)
            return [("source", label, None)] if label else []
        causes = []
        for upstream in caused_by:
            causes.extend(_root_causes(upstream, statuses, seen))
        return causes

    return []


def _variable_label(lang, table_name, variable_id):
    """Human-readable name for a BCRA variable, e.g. 'Monetary Base (variable #15)',
    falling back to just the id if the table isn't in _TABLE_LABELS."""
    name = _TABLE_LABELS.get(table_name, {}).get(lang)
    return f"{name} (variable #{variable_id})" if name else f"variable #{variable_id}"


def _data_warnings(lang, table_names, statuses):
    """Build the list of rendered warning messages for a page, given the
    table_names it depends on and the full scrape_status payload."""
    sources_url = "/en/sources" if lang == "en" else "/fuentes"
    messages = []
    seen_causes = set()

    def add(msg):
        if msg not in messages:
            messages.append(msg)

    for table_name in table_names:
        row = statuses.get(table_name)
        if not row or row.get("status") == "ok":
            continue
        kind = row.get("source_kind")
        status = row.get("status")

        if kind == "bcra_variable":
            link = row.get("source_url")
            label = _variable_label(lang, table_name, row.get("variable_id"))
            if status == "error":
                if lang == "en":
                    msg = format_html(
                        'The BCRA API is returning an error ({}) for {}. '
                        '<a href="{}" target="_blank" rel="noopener">See the BCRA API</a>.',
                        row.get("error_code") or "?", label, link,
                    )
                else:
                    msg = format_html(
                        'La API del BCRA está devolviendo un error ({}) para {}. '
                        '<a href="{}" target="_blank" rel="noopener">Ver la API del BCRA</a>.',
                        row.get("error_code") or "?", label, link,
                    )
            else:
                if lang == "en":
                    msg = format_html(
                        'The BCRA API has not published new data for {} in over {} days '
                        '(last value: {}). <a href="{}" target="_blank" rel="noopener">See the BCRA API</a>.',
                        label, _STALE_THRESHOLD_DAYS, row.get("last_success_date"), link,
                    )
                else:
                    msg = format_html(
                        'La API del BCRA no publica datos nuevos para {} hace más de {} días '
                        '(último valor: {}). <a href="{}" target="_blank" rel="noopener">Ver la API del BCRA</a>.',
                        label, _STALE_THRESHOLD_DAYS, row.get("last_success_date"), link,
                    )
            add(msg)
            continue

        if kind in ("cronista", "yahoo"):
            if status == "error":
                msg = ("We have not been able to fetch this data."
                       if lang == "en" else "No hemos podido obtener estos datos.")
            elif lang == "en":
                msg = format_html(
                    "This data has not been updated in over {} days (last value: {}).",
                    _STALE_THRESHOLD_DAYS, row.get("last_success_date"),
                )
            else:
                msg = format_html(
                    "Estos datos no se actualizan hace más de {} días (último valor: {}).",
                    _STALE_THRESHOLD_DAYS, row.get("last_success_date"),
                )
            add(msg)
            continue

        if kind == "calculated":
            causes = _root_causes(table_name, statuses)
            if not causes:
                msg = ("This calculated value may be out of date." if lang == "en"
                       else "Este valor calculado puede estar desactualizado.")
                add(msg)
                continue
            for cause_type, cause_value, cause_table in causes:
                cause_key = (cause_type, cause_value)
                if cause_key in seen_causes:
                    continue
                seen_causes.add(cause_key)
                if cause_type == "variable":
                    label = _variable_label(lang, cause_table, cause_value)
                    if lang == "en":
                        msg = format_html(
                            'This value may be affected because {} has stale or missing data at the '
                            'BCRA API. See the <a href="{}">Sources</a> page for details on where each '
                            'report\'s data comes from.',
                            label, sources_url,
                        )
                    else:
                        msg = format_html(
                            'Este valor puede estar afectado porque {} tiene datos desactualizados o '
                            'faltantes en la API del BCRA. Consultá la página de <a href="{}">Fuentes</a> '
                            'para más detalles sobre el origen de los datos de cada reporte.',
                            label, sources_url,
                        )
                else:
                    if lang == "en":
                        msg = format_html(
                            'This value may be affected because the {} data could not be fetched or is '
                            'stale. See the <a href="{}">Sources</a> page for details on where each '
                            'report\'s data comes from.',
                            cause_value, sources_url,
                        )
                    else:
                        msg = format_html(
                            'Este valor puede estar afectado porque no se pudieron obtener o están '
                            'desactualizados los datos de {}. Consultá la página de <a href="{}">Fuentes</a> '
                            'para más detalles sobre el origen de los datos de cada reporte.',
                            cause_value, sources_url,
                        )
                add(msg)

    return messages


def _cache_headers(response):
    if not settings.DEBUG:
        response["Cache-Control"] = "max-age=14400, public"
    return response


def home(request):
    ctx = _ctx(request, "home")
    ctx["variations"] = _fetch_variations("/var_base_res")
    ctx["scrape_statuses"] = {row["table_name"]: row for row in _fetch_scrape_status()}
    response = render(request, "portal/pages/home.html", ctx)
    return _cache_headers(response)


def report(request, page):
    ctx = _ctx(request, page)
    if page in _VARIATIONS_PATHS:
        ctx["variations"] = _fetch_variations(_VARIATIONS_PATHS[page])
    if page in _CHART_PAGES:
        ctx["scrape_statuses"] = {row["table_name"]: row for row in _fetch_scrape_status()}
    response = render(request, f"portal/pages/{page}.html", ctx)
    return _cache_headers(response)


_STATUS_PAGE_LABELS = {
    "es": {"error": "Error", "stale": "Datos desactualizados", "fetch_error": "Error de obtención"},
    "en": {"error": "Error", "stale": "Stale data", "fetch_error": "Fetching error"},
}


def _status_rows(lang, statuses):
    """Rows for the status page: every fetched (non-calculated) table whose
    last scrape isn't "ok". Calculated tables are left out — their status only
    mirrors the upstream source that's already listed."""
    labels = _STATUS_PAGE_LABELS[lang]
    rows = []
    for row in statuses:
        kind = row.get("source_kind")
        status = row.get("status")
        if kind == "calculated" or status == "ok":
            continue
        table_name = row["table_name"]

        if kind == "bcra_variable":
            variable_id = row.get("variable_id")
            name = _TABLE_LABELS.get(table_name, {}).get(lang, table_name)
            name = f"{name} (#{variable_id})"
            if status == "stale":
                status_label = labels["stale"]
            else:
                code = row.get("error_code")
                status_label = f'{labels["error"]} {code}' if code else labels["error"]
            sort_key = (0, variable_id or 0)
        else:
            name = f"{_SOURCE_LABELS.get(table_name, table_name)} ({kind.title()})"
            status_label = labels["stale"] if status == "stale" else labels["fetch_error"]
            sort_key = (1, name)

        rows.append({
            "sort_key": sort_key,
            "name": name,
            "status": status_label,
            "last_fetched": row.get("checked_date"),
            "last_ingested": row.get("last_ingested_date"),
        })
    rows.sort(key=lambda r: r["sort_key"])
    return rows


def status(request):
    ctx = _ctx(request, "status")
    ctx["status_rows"] = _status_rows(ctx["lang"], _fetch_scrape_status())
    response = render(request, "portal/pages/status.html", ctx)
    if not settings.DEBUG:
        response["Cache-Control"] = "max-age=300, public"
    return response


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
