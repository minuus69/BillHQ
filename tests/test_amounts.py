"""Amounts must be read exactly or rejected, never guessed."""
from decimal import Decimal

import pytest

from appdata.csvparser import amount_decimal, parse_amount


@pytest.mark.parametrize("text, expected", [
    ("12.50", "12.50"), ("12,50", "12.50"), ("79.9", "79.9"), ("1250", "1250"),
    ("1'250.50", "1250.50"), ("1’250,50", "1250.50"), ("1 250", "1250"), ("0", "0"),
])
def test_accepted(text, expected):
    assert parse_amount(text) == Decimal(expected)


@pytest.mark.parametrize("text", [
    "1,250", "1.250", "1,250.00", "NaN", "Infinity", "-Infinity", "-5", "1e3", "", "abc", "12.",
])
def test_rejected(text):
    with pytest.raises(ValueError):
        parse_amount(text)


@pytest.mark.parametrize("stored, expected", [
    ("79.90", "79.90"), ("", "0"), ("junk", "0"), ("NaN", "0"), ("sNaN", "0"), ("Infinity", "0"),
])
def test_stored_values_never_break_totals(stored, expected):
    assert amount_decimal(stored) == Decimal(expected)
    assert sum([amount_decimal(stored)], Decimal(0)) == Decimal(expected)
