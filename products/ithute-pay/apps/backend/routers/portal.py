from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.access_control import MerchantContext, get_merchant_context
from database.session import get_db
from integrations.mpesa.contracts import normalize_mpesa_capabilities
from integrations.mpesa.sandbox_matrix import MPESA_DOCUMENTED_NOT_RUNNABLE, MPESA_OFFICIAL_SANDBOX_MATRIX, sandbox_case
from routers import mpesa_certification as certification
from routers import testing as legacy_testing
from services.audit import write_audit
from utils.helpers import public_id, utcnow


router = APIRouter(prefix='/portal', tags=['Partner Testing Portal'])


class PortalMpesaRunRequest(BaseModel):
    product: str = Field(min_length=1, max_length=64)
    scenario: str = Field(min_length=1, max_length=64)
    amount: Decimal = Field(default=Decimal('25.00'), gt=0, le=Decimal('1000000.00'))
    currency: str = Field(default='LSL', min_length=3, max_length=3)
    voucher_code: str | None = Field(default=None, min_length=4, max_length=64)
    commit: bool = True


def _require_test_application(context: MerchantContext) -> None:
    environment = str(context.application.environment or '').strip().lower()
    if environment not in {'test', 'sandbox'}:
        raise HTTPException(
            status_code=403,
            detail='The partner testing portal accepts sandbox/test application API keys only.',
        )


def _safe_catalog(db: Session) -> dict[str, Any]:
    config, missing = legacy_testing._live_gateway_readiness(db)
    sandbox_configured = bool(config and str(config.environment).strip().lower() == 'sandbox')
    capabilities = normalize_mpesa_capabilities((config.metadata_json or {}).get('capabilities') if config else None)
    services = {
        product: {
            'label': spec.get('label', product),
            'capability': spec.get('capability'),
            'input_field': spec.get('input_field'),
            'requires_voucher_code': bool(spec.get('requires_voucher_code')),
            'cases': spec.get('cases') or {},
        }
        for product, spec in MPESA_OFFICIAL_SANDBOX_MATRIX.items()
    }
    return {
        'provider': 'mpesa',
        'environment': 'sandbox',
        'ready': bool(sandbox_configured and not missing),
        'missing': missing if sandbox_configured else ['active sandbox provider configuration'],
        'capabilities': capabilities,
        'services': services,
        'documented_not_runnable': MPESA_DOCUMENTED_NOT_RUNNABLE,
        'safety': {
            'live_funds': False,
            'production_credentials_exposed': False,
            'api_key_environment': 'test',
        },
    }


@router.get('/context')
def portal_context(context: MerchantContext = Depends(get_merchant_context)):
    _require_test_application(context)
    return {
        'merchant': {'id': context.merchant.id, 'name': context.merchant.name, 'slug': context.merchant.slug},
        'application': {
            'id': context.application.id,
            'name': context.application.name,
            'environment': context.application.environment,
        },
        'api_key': {'id': context.api_key.id, 'name': context.api_key.name, 'last4': context.api_key.last4},
        'portal_role': 'consumer_tester',
    }


@router.get('/testing/catalog')
def testing_catalog(
    db: Session = Depends(get_db),
    context: MerchantContext = Depends(get_merchant_context),
):
    _require_test_application(context)
    return _safe_catalog(db)


@router.post('/testing/mpesa/run')
async def run_mpesa_test(
    payload: PortalMpesaRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    context: MerchantContext = Depends(get_merchant_context),
):
    _require_test_application(context)
    try:
        product_spec, _case = sandbox_case(payload.product, payload.scenario)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f'Unknown M-Pesa sandbox test case: {exc.args[0]}') from None

    config, provider = certification._configured_provider(db)
    certification._require_capability(config, product_spec)
    certification_payload = certification.MpesaCertificationRunRequest(
        product=payload.product,
        scenario=payload.scenario,
        amount=payload.amount,
        currency=payload.currency.upper(),
        voucher_code=payload.voucher_code,
        commit=payload.commit,
    )

    started = time.perf_counter()
    result = await certification._execute_case(provider, payload.product, payload.scenario, certification_payload)
    result['duration_ms'] = round((time.perf_counter() - started) * 1000, 2)
    result['executed_at'] = utcnow().isoformat()
    result['environment'] = 'sandbox'
    result['provider'] = 'mpesa'
    result['shortcode'] = config.service_provider_code
    run_id = public_id('portaltest')
    result['run_id'] = run_id

    write_audit(
        db,
        actor_type='api_key',
        actor_id=context.api_key.id,
        action='partner_portal.mpesa_test.executed',
        resource_type='partner_portal_test',
        resource_id=run_id,
        merchant_id=context.merchant.id,
        ip_address=request.client.host if request.client else None,
        metadata={
            'application_id': context.application.id,
            'product': payload.product,
            'scenario': payload.scenario,
            'passed': result.get('passed'),
            'status': (result.get('result') or {}).get('status'),
            'response_code': (result.get('result') or {}).get('response_code'),
        },
    )
    db.commit()
    return result
