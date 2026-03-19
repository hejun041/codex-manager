import asyncio
from types import SimpleNamespace

from src.core import scheduler as scheduler_core
from src.web.routes import scheduler as scheduler_route


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def test_test_cliproxy_auth_file_marks_rate_limited_response_invalid(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, "kwargs": kwargs})
        return FakeResponse(
            status_code=200,
            payload={
                "status_code": 200,
                "body": (
                    '{"rate_limit": {"allowed": false, "limit_reached": true}}'
                ),
            },
        )

    monkeypatch.setattr(scheduler_core.cffi_requests, "post", fake_post)
    monkeypatch.setattr(
        scheduler_core,
        "get_settings",
        lambda: SimpleNamespace(
            cpa_auto_check_test_url="https://chatgpt.com/backend-api/wham/usage",
            cpa_auto_check_test_model="gpt-5.3-codex",
            cpa_auto_check_min_remaining_weekly_percent=20,
        ),
    )

    success, message = scheduler_core.test_cliproxy_auth_file(
        {
            "name": "demo.json",
            "auth_index": "auth-123",
            "id_token": {"chatgpt_account_id": "acct-123"},
        },
        api_url="https://cpa.example.com",
        api_token="token-123",
    )

    assert success is False
    assert "rate_limit" in message
    assert calls[0]["url"] == "https://cpa.example.com/v0/management/api-call"
    assert calls[0]["kwargs"]["json"]["header"]["Chatgpt-Account-Id"] == "acct-123"


def test_test_cliproxy_auth_file_marks_low_remaining_weekly_quota_invalid(monkeypatch):
    def fake_post(url, **kwargs):
        return FakeResponse(
            status_code=200,
            payload={
                "status_code": 200,
                "body": (
                    '{"rate_limit": {"allowed": true, "limit_reached": false,'
                    ' "primary_window": {"used_percent": 81}}}'
                ),
            },
        )

    monkeypatch.setattr(scheduler_core.cffi_requests, "post", fake_post)
    monkeypatch.setattr(
        scheduler_core,
        "get_settings",
        lambda: SimpleNamespace(
            cpa_auto_check_test_url="https://chatgpt.com/backend-api/wham/usage",
            cpa_auto_check_test_model="gpt-5.3-codex",
            cpa_auto_check_min_remaining_weekly_percent=20,
        ),
    )

    success, message = scheduler_core.test_cliproxy_auth_file(
        {"name": "demo.json", "auth_index": "auth-123"},
        api_url="https://cpa.example.com",
        api_token="token-123",
    )

    assert success is False
    assert "remaining_percent=19" in message
    assert "threshold=20" in message


def test_test_cliproxy_auth_file_allows_low_remaining_quota_when_threshold_disabled(monkeypatch):
    def fake_post(url, **kwargs):
        return FakeResponse(
            status_code=200,
            payload={
                "status_code": 200,
                "body": (
                    '{"rate_limit": {"allowed": true, "limit_reached": false,'
                    ' "primary_window": {"used_percent": 81}}}'
                ),
            },
        )

    monkeypatch.setattr(scheduler_core.cffi_requests, "post", fake_post)
    monkeypatch.setattr(
        scheduler_core,
        "get_settings",
        lambda: SimpleNamespace(
            cpa_auto_check_test_url="https://chatgpt.com/backend-api/wham/usage",
            cpa_auto_check_test_model="gpt-5.3-codex",
            cpa_auto_check_min_remaining_weekly_percent=0,
        ),
    )

    success, message = scheduler_core.test_cliproxy_auth_file(
        {"name": "demo.json", "auth_index": "auth-123"},
        api_url="https://cpa.example.com",
        api_token="token-123",
    )

    assert success is True
    assert message == "status_code=200"


def test_test_cliproxy_auth_file_marks_unavailable_item_invalid(monkeypatch):
    def fail_post(*args, **kwargs):
        raise AssertionError("unavailable 凭证不应继续调用 api-call")

    monkeypatch.setattr(scheduler_core.cffi_requests, "post", fail_post)

    success, message = scheduler_core.test_cliproxy_auth_file(
        {
            "name": "demo.json",
            "auth_index": "auth-123",
            "status": "error",
            "unavailable": True,
            "status_message": '{"error": {"type": "usage_limit_reached"}}',
        },
        api_url="https://cpa.example.com",
        api_token="token-123",
    )

    assert success is False
    assert "unavailable" in message
    assert "usage_limit_reached" in message


def test_trigger_cpa_scheduler_check_passes_manual_logs_correctly(monkeypatch):
    class FakeLoop:
        async def run_in_executor(self, executor, func, *args):
            return func(*args)

    def fake_check_cpa_services_job(main_loop, manual_logs=None):
        assert main_loop is None
        assert isinstance(manual_logs, list)
        manual_logs.append("[INFO] 手动检查已执行")

    monkeypatch.setattr(scheduler_route.asyncio, "get_event_loop", lambda: FakeLoop())
    monkeypatch.setattr(scheduler_core, "check_cpa_services_job", fake_check_cpa_services_job)

    result = asyncio.run(scheduler_route.trigger_cpa_scheduler_check())

    assert result["success"] is True
    assert result["logs"] == ["[INFO] 手动检查已执行"]
