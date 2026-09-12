import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from xml.sax.saxutils import escape

import httpx

from app.core.config import settings


class ProviderConfigurationError(RuntimeError):
    pass


class ProviderRequestError(RuntimeError):
    pass


def dpo_configured() -> bool:
    return bool(settings.dpo_company_token and settings.dpo_service_type)


def dpo_create_token(*, amount_minor: int, currency: str, reference: str, description: str, customer_email: str | None = None) -> dict:
    if not dpo_configured():
        raise ProviderConfigurationError("DPO Pay is not configured")
    amount = f"{amount_minor / 100:.2f}"
    service_date = datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M")
    customer_xml = f"<customerEmail>{escape(customer_email)}</customerEmail>" if customer_email else ""
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<API3G>
  <CompanyToken>{escape(settings.dpo_company_token or "")}</CompanyToken>
  <Request>createToken</Request>
  <Transaction>
    <PaymentAmount>{amount}</PaymentAmount>
    <PaymentCurrency>{escape(currency.upper())}</PaymentCurrency>
    <CompanyRef>{escape(reference)}</CompanyRef>
    <CompanyRefUnique>1</CompanyRefUnique>
    <RedirectURL>{escape(settings.dpo_redirect_url)}</RedirectURL>
    <BackURL>{escape(settings.dpo_back_url)}</BackURL>
    <PTL>{settings.dpo_payment_time_limit_hours}</PTL>
    {customer_xml}
  </Transaction>
  <Services>
    <Service>
      <ServiceType>{escape(settings.dpo_service_type or "")}</ServiceType>
      <ServiceDescription>{escape(description[:250])}</ServiceDescription>
      <ServiceDate>{service_date}</ServiceDate>
    </Service>
  </Services>
</API3G>"""
    try:
        response = httpx.post(
            settings.dpo_api_url,
            content=xml.encode("utf-8"),
            headers={"Content-Type": "application/xml; charset=utf-8", "Accept": "application/xml"},
            timeout=settings.external_provider_timeout_seconds,
        )
        response.raise_for_status()
        root = ET.fromstring(response.text)
    except (httpx.HTTPError, ET.ParseError) as exc:
        raise ProviderRequestError(f"DPO Pay request failed: {exc}") from exc
    result = root.findtext("Result") or ""
    explanation = root.findtext("ResultExplanation") or ""
    if result != "000":
        raise ProviderRequestError(f"DPO Pay rejected transaction ({result}): {explanation}")
    token = root.findtext("TransToken")
    if not token:
        raise ProviderRequestError("DPO Pay response did not contain TransToken")
    template = settings.dpo_checkout_url
    checkout_url = template.replace("{token}", token) if "{token}" in template else f"{template}{token}"
    return {
        "provider": "dpo",
        "token": token,
        "reference": root.findtext("TransRef"),
        "checkout_url": checkout_url,
        "result": result,
        "explanation": explanation,
    }


def dpo_verify_token(token: str) -> dict:
    if not dpo_configured():
        raise ProviderConfigurationError("DPO Pay is not configured")
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<API3G>
  <CompanyToken>{escape(settings.dpo_company_token or "")}</CompanyToken>
  <Request>verifyToken</Request>
  <TransactionToken>{escape(token)}</TransactionToken>
</API3G>"""
    try:
        response = httpx.post(
            settings.dpo_api_url,
            content=xml.encode("utf-8"),
            headers={"Content-Type": "application/xml; charset=utf-8", "Accept": "application/xml"},
            timeout=settings.external_provider_timeout_seconds,
        )
        response.raise_for_status()
        root = ET.fromstring(response.text)
    except (httpx.HTTPError, ET.ParseError) as exc:
        raise ProviderRequestError(f"DPO Pay verification failed: {exc}") from exc
    return {child.tag: (child.text or "") for child in root}


def opensrs_configured() -> bool:
    return bool(settings.opensrs_username and settings.opensrs_api_key)


def _simple_item(key: str, value: str) -> str:
    return f'<item key="{escape(key)}">{escape(value)}</item>'


def _assoc_item(key: str, values: dict[str, str]) -> str:
    inner = "".join(_simple_item(k, str(v)) for k, v in values.items() if v is not None)
    return f'<item key="{escape(key)}"><dt_assoc>{inner}</dt_assoc></item>'


def _array_item(key: str, values: list[str]) -> str:
    inner = "".join(_simple_item(str(i), value) for i, value in enumerate(values))
    return f'<item key="{escape(key)}"><dt_array>{inner}</dt_array></item>'


def _opensrs_envelope(action: str, attributes_xml: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<OPS_envelope><header><version>0.9</version></header><body><data_block><dt_assoc>
{_simple_item("protocol", "XCP")}
{_simple_item("action", action.upper())}
{_simple_item("object", "DOMAIN")}
<item key="attributes"><dt_assoc>{attributes_xml}</dt_assoc></item>
</dt_assoc></data_block></body></OPS_envelope>"""


def _opensrs_send(action: str, attributes_xml: str) -> dict:
    if not opensrs_configured():
        raise ProviderConfigurationError("OpenSRS is not configured")
    xml = _opensrs_envelope(action, attributes_xml)
    key = settings.opensrs_api_key or ""
    first = hashlib.md5((xml + key).encode("utf-8")).hexdigest()
    signature = hashlib.md5((first + key).encode("utf-8")).hexdigest()
    try:
        response = httpx.post(
            settings.opensrs_api_url,
            content=xml.encode("utf-8"),
            headers={"Content-Type": "text/xml", "X-Username": settings.opensrs_username or "", "X-Signature": signature},
            timeout=settings.external_provider_timeout_seconds,
        )
        response.raise_for_status()
        parsed = ET.fromstring(response.text)
    except (httpx.HTTPError, ET.ParseError) as exc:
        raise ProviderRequestError(f"OpenSRS request failed: {exc}") from exc

    items: dict[str, str] = {}
    for item in parsed.findall(".//item"):
        key_name = item.attrib.get("key")
        if key_name and len(item) == 0:
            items[key_name] = item.text or ""
    if items.get("is_success") != "1":
        raise ProviderRequestError(f"OpenSRS rejected request: {items.get('response_text', 'unknown error')}")
    return items


def opensrs_lookup(domain: str) -> dict:
    return _opensrs_send("LOOKUP", _simple_item("domain", domain))


def _contact(name: str, email: str, phone: str, address: str, city: str, country: str, postal_code: str) -> dict[str, str]:
    parts = name.strip().split(None, 1)
    first = parts[0]
    last = parts[1] if len(parts) > 1 else parts[0]
    return {
        "first_name": first,
        "last_name": last,
        "email": email,
        "phone": phone,
        "address1": address,
        "city": city,
        "country": country.upper(),
        "postal_code": postal_code,
    }


def opensrs_register(
    *,
    domain: str,
    years: int,
    registrant_username: str,
    registrant_password: str,
    nameserver_1: str,
    nameserver_2: str,
    owner_name: str,
    owner_email: str,
    owner_phone: str,
    owner_address: str,
    owner_city: str,
    owner_country: str,
    owner_postal_code: str,
) -> dict:
    contact = _contact(owner_name, owner_email, owner_phone, owner_address, owner_city, owner_country, owner_postal_code)
    contact_set = (
        '<item key="contact_set"><dt_assoc>'
        + _assoc_item("owner", contact)
        + _assoc_item("admin", contact)
        + _assoc_item("billing", contact)
        + "</dt_assoc></item>"
    )
    attrs = "".join([
        _simple_item("domain", domain),
        _simple_item("reg_type", "new"),
        _simple_item("period", str(years)),
        _simple_item("handle", "process"),
        _simple_item("auto_renew", "1"),
        _simple_item("reg_username", registrant_username),
        _simple_item("reg_password", registrant_password),
        _simple_item("f_whois_privacy", "1"),
        _simple_item("custom_nameservers", "1"),
        _array_item("nameserver_list", [nameserver_1, nameserver_2]),
        contact_set,
    ])
    return _opensrs_send("SW_REGISTER", attrs)
