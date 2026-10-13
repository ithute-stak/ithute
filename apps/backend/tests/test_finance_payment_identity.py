"""Regression checks for official Ithute finance payment identity."""
from pathlib import Path

from app.services import finance_branding, finance_invoices, finance_invoice_v2


def test_mpesa_identity_is_shared_across_pdf_templates():
    assert finance_branding.MPESA_NUMBER == "59001394"
    assert finance_branding.MPESA_NAME == "Koetlisi Theko"
    assert finance_invoice_v2.MPESA_NUMBER == finance_branding.MPESA_NUMBER
    assert finance_invoice_v2.MPESA_NAME == finance_branding.MPESA_NAME


def test_bank_payment_information_is_centralized():
    assert finance_invoices.BANK_NAME == "LPB"
    assert finance_invoices.BANK_ACCOUNT_NAME == "Koetlisi Theko"
    assert finance_invoices.BANK_ACCOUNT_NUMBER == "1035927000011"
    assert finance_invoice_v2.BANK_ACCOUNT_NUMBER == finance_invoices.BANK_ACCOUNT_NUMBER


def test_approved_finance_artwork_is_bundled():
    assert finance_branding.ASSET.is_file(), "Approved header must ship in backend image"
    assert finance_branding.SIGNATURE_ASSET.is_file(), "Signed finance documents need approved signature"
    finance_branding.verified_signature()
