from bambu_p1s_mcp.redact import public_error, redact


def test_redact_access_code():
    assert redact("login with 12ab34cd failed", "12ab34cd") == "login with *** failed"


def test_public_error():
    text = public_error(RuntimeError("password 12ab34cd"), "12ab34cd")
    assert "12ab34cd" not in text
    assert "RuntimeError" in text
