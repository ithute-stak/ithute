from database.session import SessionLocal
from database.models import ApiKey, Application, Merchant
from core.security import generate_secret, sha256_text


def test_partner_portal_context_accepts_sandbox_application_key(client, merchant_api_key):
    response = client.get(
        '/api/v1/portal/context',
        headers={'Authorization': f'Bearer {merchant_api_key}'},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['portal_role'] == 'consumer_tester'
    assert payload['application']['environment'] == 'test'
    assert payload['merchant']['name'] == 'LoanHub'


def test_partner_portal_catalog_exposes_consumer_test_products(client, merchant_api_key):
    response = client.get(
        '/api/v1/portal/testing/catalog',
        headers={'Authorization': f'Bearer {merchant_api_key}'},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['environment'] == 'sandbox'
    assert payload['safety']['live_funds'] is False
    assert payload['safety']['production_credentials_exposed'] is False
    assert {'c2b', 'b2c', 'b2b', 'reversal', 'direct_debit_create'}.issubset(payload['services'])


def test_partner_portal_rejects_live_application_key(client):
    secret = generate_secret('ipb_live_', 16)
    with SessionLocal() as db:
        merchant = Merchant(name='Live Partner', slug='live-partner')
        db.add(merchant)
        db.flush()
        application = Application(merchant_id=merchant.id, name='Live App', environment='live')
        db.add(application)
        db.flush()
        key = ApiKey(
            application_id=application.id,
            name='Live key',
            prefix=secret[:16],
            secret_hash=sha256_text(secret),
            last4=secret[-4:],
            scopes=[],
        )
        db.add(key)
        db.commit()

    response = client.get(
        '/api/v1/portal/context',
        headers={'Authorization': f'Bearer {secret}'},
    )
    assert response.status_code == 403
    assert 'sandbox/test' in response.json()['detail']
