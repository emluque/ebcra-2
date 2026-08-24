from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path("", views.home, name="home_en"),
    # Monetary base
    path("argentina_monetary_base",                                                   views.report, {"page": "base"},           name="base_en"),
    path("argentina_monetary_base_in_usd",                                            views.report, {"page": "base_usd"},        name="base_usd_en"),
    path("argentina_monetary_base_divided_by_international_reserves",                 views.report, {"page": "base_div_res"},    name="base_div_res_en"),
    path("argentina_monetary_base_components",                                        views.report, {"page": "componentes"},     name="componentes_en"),
    # Reserves
    path("argentina_international_reserves",                                          views.report, {"page": "reservas"},            name="reservas_en"),
    path("argentina_international_reserves_composition",                              views.report, {"page": "comp_reservas"},        name="comp_reservas_en"),
    path("argentina_international_reserves_variation_factors",                        views.report, {"page": "fact_var_reservas"},    name="fact_var_reservas_en"),
    # Deposits / loans
    path("argentina_deposits",                                                        views.report, {"page": "depositos"},        name="depositos_en"),
    path("argentina_deposits_by_sector",                                              views.report, {"page": "depositos_sector"}, name="depositos_sector_en"),
    path("argentina_usd_deposits",                                                    views.report, {"page": "depositos_usd"},                    name="depositos_usd_en"),
    path("argentina_deposits_by_holder",                                              views.report, {"page": "depositos_titular"},                name="depositos_titular_en"),
    path("argentina_financial_system_liquidity",                                      views.report, {"page": "liquidez_sistema_financiero"},      name="liquidez_sistema_financiero_en"),
    path("argentina_m1",                                                              views.report, {"page": "m1_argentina"},    name="m1_argentina_en"),
    path("argentina_m1_in_usd",                                                       views.report, {"page": "m1_usd"},          name="m1_usd_en"),
    path("argentina_m1_divided_by_international_reserves",                            views.report, {"page": "m1_div_res"},      name="m1_div_res_en"),
    path("argentina_m2",                                                              views.report, {"page": "m2_argentina"},    name="m2_argentina_en"),
    path("argentina_m2_in_usd",                                                       views.report, {"page": "m2_usd"},          name="m2_usd_en"),
    path("argentina_m2_divided_by_international_reserves",                            views.report, {"page": "m2_div_res"},      name="m2_div_res_en"),
    path("argentina_m3",                                                              views.report, {"page": "m3_argentina"},    name="m3_argentina_en"),
    path("argentina_m3_in_usd",                                                       views.report, {"page": "m3_usd"},          name="m3_usd_en"),
    path("argentina_m3_divided_by_international_reserves",                            views.report, {"page": "m3_div_res"},      name="m3_div_res_en"),
    path("argentina_loans",                                                           views.report, {"page": "prestamos"},           name="prestamos_en"),
    path("argentina_loans_by_type",                                                   views.report, {"page": "prestamos_por_tipo"},  name="prestamos_por_tipo_en"),
    path("argentina_mortgage_and_secured_loans",                                       views.report, {"page": "hipotecarios_prendarios"}, name="hipotecarios_prendarios_en"),
    path("argentina_loans_by_borrower",                                                views.report, {"page": "prestamos_titular"},         name="prestamos_titular_en"),
    path("argentina_percentage_loans_vs_deposits",                                    views.report, {"page": "porc_prestamos"},      name="porc_prestamos_en"),
    # Interest rates
    path("argentina_interest_rates",                                                  views.report, {"page": "tasas"},           name="tasas_en"),
    path("argentina_lending_interest_rates",                                          views.report, {"page": "tasas_prestamos"}, name="tasas_prestamos_en"),
    path("argentina_deposit_interest_rates",                                          views.report, {"page": "tasas_depositos"}, name="tasas_depositos_en"),
    # CER / UVA / UVI
    path("cer",                                                                       views.report, {"page": "cer"},             name="cer_en"),
    path("unit_of_purchasing_value",                                                  views.report, {"page": "uva"},             name="uva_en"),
    path("unit_of_dwelling",                                                          views.report, {"page": "uvi"},             name="uvi_en"),
    path("icl",                                                                       views.report, {"page": "icl"},             name="icl_en"),
    # Inflation
    path("argentina_monthly_inflation",                                               views.report, {"page": "inf_mensual"},     name="inf_mensual_en"),
    path("argentina_annual_inflation",                                                views.report, {"page": "inf_interanual"},  name="inf_interanual_en"),
    path("argentina_expected_inflation",                                              views.report, {"page": "inf_esperada"},    name="inf_esperada_en"),
    # Pases
    path("argentina_repo_operations",                                                     views.report, {"page": "pases"},           name="pases_en"),
    path("fiscal_monetary_interface",                                                     views.report, {"page": "interfaz_fiscal_monetaria"}, name="interfaz_fiscal_monetaria_en"),
    # Merval
    path("merval_index",                                                              views.report, {"page": "merval"},          name="merval_en"),
    path("merval_in_usd",                                                             views.report, {"page": "merval_usd"},      name="merval_usd_en"),
    # Profitability
    path("argentina_annual_profitability",                                            views.report, {"page": "rentabilidades"},  name="rentabilidades_en"),
    path("argentina_anual_dollar_profit",                                             RedirectView.as_view(url="/en/argentina_annual_profitability", permanent=True)),
    path("argentina_anual_official_dollar_profit",                                    RedirectView.as_view(url="/en/argentina_annual_profitability", permanent=True)),
    path("argentina_anual_merval_profit",                                             RedirectView.as_view(url="/en/argentina_annual_profitability", permanent=True)),
    # Plain text pages
    path("sources",                                                                   views.report, {"page": "sources"},        name="sources_en"),
    path("credits",                                                                   views.report, {"page": "credits"},        name="credits_en"),
    path("note_on_inflation_data",                                                    views.report, {"page": "nota_inflacion"}, name="nota_inflacion_en"),
    path("release_notes",                                                             views.report, {"page": "release_notes"},  name="release_notes_en"),
    path("error",                                                                     views.error_page,                         name="error_en"),
]
