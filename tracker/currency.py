"""Pay in many currencies.

Postings pay in their own country's currency: rupees in India, zloty in
Poland, Singapore dollars in Singapore. Ghostless keeps pay in the currency
the posting states (or, when it doesn't say, the currency of the posting's
country) and shows it that way.

TO_USD holds rough rates to US dollars, only for comparing amounts: telling
whether an amount fits an hour, a month or a year, and sorting by pay. They
are never shown, and being 10-20% off doesn't change either use. Review them
once a year.
"""

from __future__ import annotations

TO_USD: dict[str, float] = {
    "USD": 1.0, "CAD": 0.73, "GBP": 1.27, "EUR": 1.08, "AUD": 0.66, "NZD": 0.60, "CHF": 1.12,
    "SEK": 0.095, "NOK": 0.093, "DKK": 0.145, "PLN": 0.25, "CZK": 0.043, "HUF": 0.0027, "RON": 0.22,
    "BGN": 0.55, "TRY": 0.03, "ILS": 0.27, "AED": 0.27, "SAR": 0.27, "QAR": 0.27, "ZAR": 0.054,
    "EGP": 0.02, "NGN": 0.00065, "KES": 0.0077, "INR": 0.012, "PKR": 0.0036, "BDT": 0.0084,
    "LKR": 0.0033, "SGD": 0.74, "HKD": 0.128, "CNY": 0.14, "TWD": 0.031, "JPY": 0.0067, "KRW": 0.00073,
    "PHP": 0.017, "THB": 0.028, "VND": 0.00004, "IDR": 0.000063, "MYR": 0.21, "MXN": 0.055,
    "BRL": 0.18, "ARS": 0.001, "CLP": 0.0011, "COP": 0.00025, "PEN": 0.27, "UYU": 0.025, "CRC": 0.0019,
}  # fmt: skip

# the currency of a posting's country, for pay that doesn't name one
COUNTRY_CURRENCY: dict[str, str] = {
    "US": "USD", "CA": "CAD", "GB": "GBP", "IE": "EUR", "FR": "EUR", "DE": "EUR", "NL": "EUR",
    "BE": "EUR", "LU": "EUR", "ES": "EUR", "PT": "EUR", "IT": "EUR", "AT": "EUR", "FI": "EUR",
    "GR": "EUR", "EE": "EUR", "LV": "EUR", "LT": "EUR", "SK": "EUR", "SI": "EUR", "HR": "EUR",
    "MT": "EUR", "CY": "EUR", "AU": "AUD", "NZ": "NZD", "CH": "CHF", "SE": "SEK", "NO": "NOK",
    "DK": "DKK", "PL": "PLN", "CZ": "CZK", "HU": "HUF", "RO": "RON", "BG": "BGN", "TR": "TRY",
    "IL": "ILS", "AE": "AED", "SA": "SAR", "QA": "QAR", "ZA": "ZAR", "EG": "EGP", "NG": "NGN",
    "KE": "KES", "IN": "INR", "PK": "PKR", "BD": "BDT", "LK": "LKR", "SG": "SGD", "HK": "HKD",
    "CN": "CNY", "TW": "TWD", "JP": "JPY", "KR": "KRW", "PH": "PHP", "TH": "THB", "VN": "VND",
    "ID": "IDR", "MY": "MYR", "MX": "MXN", "BR": "BRL", "AR": "ARS", "CL": "CLP", "CO": "COP",
    "PE": "PEN", "UY": "UYU", "CR": "CRC",
}  # fmt: skip

# where a bare "$" is the country's own dollar; elsewhere it's the US dollar
DOLLAR_COUNTRIES = {"US": "USD", "CA": "CAD", "AU": "AUD", "NZ": "NZD", "SG": "SGD", "HK": "HKD"}


def known(currency: str | None) -> bool:
    return currency in TO_USD


def of_country(country: str | None) -> str | None:
    return COUNTRY_CURRENCY.get(country or "")


def to_usd(amount: float, currency: str | None) -> float:
    """Roughly what an amount is in US dollars; an unlabelled amount counts as dollars."""
    return amount * TO_USD.get(currency or "USD", 1.0)


def usd_case_sql(column: str) -> str:
    """SQL for the rate to US dollars of a currency column, for sorting by pay."""
    whens = " ".join(f"WHEN '{code}' THEN {rate}" for code, rate in TO_USD.items())
    return f"CASE {column} {whens} ELSE 1 END"
