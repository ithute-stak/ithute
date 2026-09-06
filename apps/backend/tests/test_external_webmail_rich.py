from app.api.v1.external_webmail_rich import _sanitize_html


def test_rich_mail_sanitizer_keeps_editor_formatting_and_removes_active_content():
    source = """
    <div style="text-align:center;position:fixed" onclick="steal()">
      <strong>Hello</strong>
      <script>alert('x')</script>
      <a href="javascript:alert(1)">unsafe</a>
      <a href="https://ithute.co.ls" style="color:#123456">Ithute</a>
      <img src="https://tracker.example/pixel.gif" onerror="steal()">
    </div>
    """

    sanitized = _sanitize_html(source)

    assert "<strong>Hello</strong>" in sanitized
    assert "text-align:center" in sanitized
    assert "position:fixed" not in sanitized
    assert "onclick" not in sanitized
    assert "<script" not in sanitized
    assert "javascript:" not in sanitized
    assert 'href="https://ithute.co.ls"' in sanitized
    assert "<img" not in sanitized
    assert "onerror" not in sanitized


def test_rich_mail_sanitizer_allows_mailto_links_but_not_data_urls():
    sanitized = _sanitize_html(
        '<a href="mailto:hello@ithute.co.ls">Mail us</a>'
        '<a href="data:text/html,bad">Bad</a>'
    )

    assert 'href="mailto:hello@ithute.co.ls"' in sanitized
    assert "data:text/html" not in sanitized
