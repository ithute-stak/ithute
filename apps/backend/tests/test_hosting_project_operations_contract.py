import pytest
from pydantic import ValidationError

from app.api.v1.hosting_project_operations import AgentProjectOperationLease, AgentProjectOperationStatus, LogRequest, MAX_LOG_OUTPUT


def test_log_request_bounds():
    assert LogRequest().lines == 300
    assert LogRequest(lines=2000).lines == 2000
    with pytest.raises(ValidationError):
        LogRequest(lines=0)
    with pytest.raises(ValidationError):
        LogRequest(lines=2001)


def test_agent_log_payload_is_bounded():
    assert AgentProjectOperationStatus(fencing_token="f" * 32, success=True, output="ok").output == "ok"
    with pytest.raises(ValidationError):
        AgentProjectOperationStatus(fencing_token="f" * 32, success=True, output="x" * (MAX_LOG_OUTPUT + 1))


def test_agent_failure_message_is_bounded():
    assert AgentProjectOperationStatus(fencing_token="f" * 32, success=False, message="failure").message == "failure"
    with pytest.raises(ValidationError):
        AgentProjectOperationStatus(fencing_token="f" * 32, success=False, message="x" * 2001)



def test_agent_lease_payload_requires_bounded_fencing_token():
    assert AgentProjectOperationLease(fencing_token="x" * 32).fencing_token == "x" * 32
    with pytest.raises(ValidationError):
        AgentProjectOperationLease(fencing_token="too-short")
