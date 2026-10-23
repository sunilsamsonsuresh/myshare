"""Money helpers shared by the API and the MCP server.

Rule: inside MyShare, money is ALWAYS an integer number of minor units
(paise for INR, cents for USD). Floats are never used, because 0.1 + 0.2 != 0.3.

Humans (and LLMs) speak in decimals ("1,200.50"), so the edges of the system
(the MCP server and the web UI) convert between the two using these helpers.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Number of decimal places per ISO-4217 currency. Unknown currencies default to 2.
CURRENCY_EXPONENT: dict[str, int] = {
    "INR": 2,
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "AUD": 2,
    "CAD": 2,
    "SGD": 2,
    "AED": 2,
    "JPY": 0,
}

CURRENCY_SYMBOL: dict[str, str] = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "AUD": "A$",
    "CAD": "C$",
    "SGD": "S$",
    "AED": "AED ",
}

SUPPORTED_CURRENCIES = tuple(CURRENCY_EXPONENT)


class MoneyError(ValueError):
    """Raised when a human-entered amount can't be turned into minor units."""


def exponent(currency: str) -> int:
    return CURRENCY_EXPONENT.get(currency.upper(), 2)


def to_minor(amount: str | int | float | Decimal, currency: str) -> int:
    """Convert a human amount ("1,200.50", 1200.5, "₹1200") to integer minor units.

    Raises MoneyError for unparseable, negative, or over-precise input
    (e.g. "10.005" INR has more decimals than paise allow).
    """
    if isinstance(amount, float):
        # Going through str() avoids binary-float artefacts like 0.1 -> 0.1000000000000000055
        amount = str(amount)
    if isinstance(amount, str):
        cleaned = amount.strip()
        for sym in sorted(set(CURRENCY_SYMBOL.values()), key=len, reverse=True):
            cleaned = cleaned.replace(sym.strip(), "")
        cleaned = cleaned.replace(",", "").replace("_", "").strip()
        for code in SUPPORTED_CURRENCIES:
            cleaned = cleaned.removeprefix(code).removesuffix(code).strip()
        try:
            value = Decimal(cleaned)
        except InvalidOperation as exc:
            raise MoneyError(
                f"'{amount}' is not a valid amount. Use a number like 1200 or 1200.50."
            ) from exc
    else:
        value = Decimal(amount)

    if not value.is_finite():
        raise MoneyError(f"'{amount}' is not a valid amount.")
    if value < 0:
        raise MoneyError("Amounts must be positive.")

    exp = exponent(currency)
    scaled = value.scaleb(exp)
    if scaled != scaled.to_integral_value():
        raise MoneyError(
            f"'{amount}' has too many decimal places for {currency.upper()} "
            f"(max {exp}). Did you mean {value.quantize(Decimal(1).scaleb(-exp), ROUND_HALF_UP)}?"
        )
    return int(scaled)


def to_decimal(minor: int, currency: str) -> Decimal:
    """Integer minor units -> Decimal major units (exact)."""
    return Decimal(minor).scaleb(-exponent(currency))


def to_decimal_str(minor: int, currency: str) -> str:
    """Integer minor units -> plain decimal string, e.g. 120050 -> '1200.50'."""
    exp = exponent(currency)
    return f"{to_decimal(minor, currency):.{exp}f}"


def format_money(minor: int, currency: str) -> str:
    """Integer minor units -> display string, e.g. 120050 INR -> '₹1,200.50'."""
    exp = exponent(currency)
    sign = "-" if minor < 0 else ""
    symbol = CURRENCY_SYMBOL.get(currency.upper(), currency.upper() + " ")
    return f"{sign}{symbol}{abs(to_decimal(minor, currency)):,.{exp}f}"
