"""Guard copyable Next.js configuration against public-secret exposure."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "frontend/app/ithute-platform/page.tsx"
SDK = ROOT.parent / "packages/ithute-auth-nextjs/src/index.ts"


def test_nextjs_setup_is_bound_to_registered_client_not_hardcoded_id():
    source = UI.read_text()
    assert '"ITHUTE_AUTH_CLIENT_ID="+app.client_id' in source
    assert "ITHUTE_AUTH_CALLBACK_URL=https://YOUR-APP-DOMAIN/api/auth/ithute/callback" in source
    assert "register the exact callback URL" in source.lower()


def test_sdk_has_explicit_server_only_guard_and_no_refresh_token_cookie():
    source = SDK.read_text()
    assert 'import "server-only"' in source
    assert "const session:Session={accessToken:tokens.access_token,expiresAt}" in source
    assert 'if (request.method !== "POST")' in source
    assert "timingSafeEqual" in source


def test_sdk_clears_pending_state_on_exchange_or_nonce_failure():
    source = SDK.read_text()
    assert 'signal:AbortSignal.timeout(10000)' in source
    assert 'if (!tokens.access_token || typeof tokens.access_token !== "string")' in source
    assert 'if (verified.payload.nonce!==pending.nonce) throw new Error' in source
    assert 'failed.cookies.delete(TEMP)' in source
