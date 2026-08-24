from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path("", views.home, name="home_es"),
    # Monetary base
    path("base_monetaria_argentina",                                                  views.report, {"page": "base"},           name="base_es"),
    path("base_monetaria_argentina_en_usd",                                           views.report, {"page": "base_usd"},        name="base_usd_es"),
    path("base_monetaria_dividida_reservas_internacionales_argentina",                views.report, {"page": "base_div_res"},    name="base_div_res_es"),
    path("componentes_base_monetaria_argentina",                                      views.report, {"page": "componentes"},     name="componentes_es"),
    # Reserves
    path("reservas_internacionales_argentina",                                        views.report, {"page": "reservas"},            name="reservas_es"),
    path("composicion_reservas_internacionales_argentina",                            views.report, {"page": "comp_reservas"},        name="comp_reservas_es"),
    path("factores_variacion_reservas_internacionales_argentina",                     views.report, {"page": "fact_var_reservas"},    name="fact_var_reservas_es"),
    # Deposits / loans
    path("depositos_argentina",                                                       views.report, {"page": "depositos"},        name="depositos_es"),
    path("depositos_por_sector_argentina",                                            views.report, {"page": "depositos_sector"}, name="depositos_sector_es"),
    path("depositos_en_dolares_argentina",                                            views.report, {"page": "depositos_usd"},                    name="depositos_usd_es"),
    path("depositos_por_titular_argentina",                                           views.report, {"page": "depositos_titular"},                name="depositos_titular_es"),
    path("liquidez_sistema_financiero_argentina",                                     views.report, {"page": "liquidez_sistema_financiero"},      name="liquidez_sistema_financiero_es"),
    path("m1",                                                                        views.report, {"page": "m1_argentina"},    name="m1_argentina_es"),
    path("m1_en_usd",                                                                 views.report, {"page": "m1_usd"},          name="m1_usd_es"),
    path("m1_dividido_reservas_internacionales_argentina",                            views.report, {"page": "m1_div_res"},      name="m1_div_res_es"),
    path("m2",                                                                        views.report, {"page": "m2_argentina"},    name="m2_argentina_es"),
    path("m2_en_usd",                                                                 views.report, {"page": "m2_usd"},          name="m2_usd_es"),
    path("m2_dividido_reservas_internacionales_argentina",                            views.report, {"page": "m2_div_res"},      name="m2_div_res_es"),
    path("m3",                                                                        views.report, {"page": "m3_argentina"},    name="m3_argentina_es"),
    path("m3_en_usd",                                                                 views.report, {"page": "m3_usd"},          name="m3_usd_es"),
    path("m3_dividido_reservas_internacionales_argentina",                            views.report, {"page": "m3_div_res"},      name="m3_div_res_es"),
    path("prestamos_argentina",                                                       views.report, {"page": "prestamos"},           name="prestamos_es"),
    path("prestamos_por_tipo_argentina",                                              views.report, {"page": "prestamos_por_tipo"},  name="prestamos_por_tipo_es"),
    path("prestamos_hipotecarios_y_prendarios_argentina",                             views.report, {"page": "hipotecarios_prendarios"}, name="hipotecarios_prendarios_es"),
    path("prestamos_por_titular_argentina",                                           views.report, {"page": "prestamos_titular"},         name="prestamos_titular_es"),
    path("porcentaje_prestamos_vs_depositos_argentina",                               views.report, {"page": "porc_prestamos"},      name="porc_prestamos_es"),
    # Interest rates
    path("tasas_de_interes_argentina",                                                views.report, {"page": "tasas"},           name="tasas_es"),
    path("tasas_de_interes_de_prestamos_argentina",                                   views.report, {"page": "tasas_prestamos"}, name="tasas_prestamos_es"),
    path("tasas_de_interes_de_depositos_argentina",                                   views.report, {"page": "tasas_depositos"}, name="tasas_depositos_es"),
    # CER / UVA / UVI
    path("cer",                                                                       views.report, {"page": "cer"},             name="cer_es"),
    path("unidad_de_valor_adquisitivo",                                               views.report, {"page": "uva"},             name="uva_es"),
    path("unidad_de_vivienda",                                                        views.report, {"page": "uvi"},             name="uvi_es"),
    path("icl",                                                                       views.report, {"page": "icl"},             name="icl_es"),
    # Inflation
    path("inflacion_mensual_argentina",                                               views.report, {"page": "inf_mensual"},     name="inf_mensual_es"),
    path("inflacion_interanual_argentina",                                            views.report, {"page": "inf_interanual"},  name="inf_interanual_es"),
    path("inflacion_esperada_argentina",                                              views.report, {"page": "inf_esperada"},    name="inf_esperada_es"),
    # Pases
    path("pases_argentina",                                                               views.report, {"page": "pases"},           name="pases_es"),
    path("interfaz_fiscal_monetaria",                                                     views.report, {"page": "interfaz_fiscal_monetaria"}, name="interfaz_fiscal_monetaria_es"),
    # Merval
    path("indice_merval",                                                             views.report, {"page": "merval"},          name="merval_es"),
    path("merval_en_dolares",                                                         views.report, {"page": "merval_usd"},      name="merval_usd_es"),
    # Profitability
    path("rentabilidades",                                                             views.report, {"page": "rentabilidades"},  name="rentabilidades_es"),
    path("rentabilidad_anual_dolar_argentina",                                        RedirectView.as_view(url="/rentabilidades", permanent=True)),
    path("rentabilidad_anual_dolar_oficial_argentina",                                RedirectView.as_view(url="/rentabilidades", permanent=True)),
    path("rentabilidad_anual_merval_argentina",                                       RedirectView.as_view(url="/rentabilidades", permanent=True)),
    # Plain text pages
    path("fuentes",                                                                   views.report, {"page": "sources"},        name="sources_es"),
    path("creditos",                                                                  views.report, {"page": "credits"},        name="credits_es"),
    path("nota_sobre_los_datos_oficiales_de_inflacion",                               views.report, {"page": "nota_inflacion"}, name="nota_inflacion_es"),
    path("release_notes",                                                             views.report, {"page": "release_notes"},  name="release_notes_es"),
    path("error",                                                                     views.error_page,                         name="error_es"),
]
