import gzip
import io
import zipfile

import pytest

from app.services import dmarc_reports


SAMPLE = b"""<?xml version="1.0"?>
<feedback>
  <report_metadata>
    <org_name>Example Reporter</org_name>
    <email>dmarc@example.test</email>
    <report_id>r-1</report_id>
    <date_range><begin>1791072000</begin><end>1791158400</end></date_range>
  </report_metadata>
  <policy_published>
    <domain>example.com</domain><adkim>s</adkim><aspf>s</aspf><p>reject</p><sp>reject</sp><pct>100</pct>
  </policy_published>
  <record>
    <row><source_ip>192.0.2.10</source_ip><count>8</count><policy_evaluated><disposition>none</disposition><dkim>pass</dkim><spf>pass</spf></policy_evaluated></row>
    <identifiers><header_from>example.com</header_from><envelope_from>example.com</envelope_from></identifiers>
  </record>
  <record>
    <row><source_ip>198.51.100.5</source_ip><count>2</count><policy_evaluated><disposition>reject</disposition><dkim>fail</dkim><spf>fail</spf></policy_evaluated></row>
    <identifiers><header_from>example.com</header_from><envelope_from>spoof.example.net</envelope_from></identifiers>
  </record>
</feedback>"""


def test_python_dmarc_reference_parser_summary():
    result = dmarc_reports.python_parse_dmarc_xml(SAMPLE)
    normalized = dmarc_reports.normalized_report(result, "example.com")

    assert normalized["metadata"]["report_id"] == "r-1"
    assert normalized["policy"]["p"] == "reject"
    assert normalized["summary"]["total_messages"] == 10
    assert normalized["summary"]["passed_messages"] == 8
    assert normalized["summary"]["failed_messages"] == 2
    assert normalized["summary"]["pass_rate_percent"] == 80.0
    assert len(normalized["records"]) == 2


def test_dmarc_domain_mismatch_is_rejected():
    result = dmarc_reports.python_parse_dmarc_xml(SAMPLE)
    with pytest.raises(dmarc_reports.DmarcReportError, match="does not match"):
        dmarc_reports.normalized_report(result, "other.example")


def test_dmarc_doctype_and_entities_are_rejected():
    payload = b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><feedback>&xxe;</feedback>'
    with pytest.raises(dmarc_reports.DmarcReportError, match="DTD/entities"):
        dmarc_reports.python_parse_dmarc_xml(payload)


def test_dmarc_gzip_and_zip_are_bounded_and_supported():
    compressed = gzip.compress(SAMPLE)
    assert dmarc_reports.extract_dmarc_xml(compressed, "report.xml.gz") == SAMPLE

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.xml", SAMPLE)
    assert dmarc_reports.extract_dmarc_xml(buffer.getvalue(), "report.zip") == SAMPLE


def test_java_failure_falls_back_to_python(monkeypatch):
    class BrokenClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def post(self, *args, **kwargs):
            raise __import__("httpx").ConnectError("offline")

    monkeypatch.setattr(dmarc_reports.httpx, "Client", BrokenClient)
    result, engine = dmarc_reports.parse_dmarc_xml(SAMPLE)

    assert engine == "python-fallback"
    assert result["summary"]["total_messages"] == 10
