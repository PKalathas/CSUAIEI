import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from guardian_client import GuardianError, end_session, start_session


def _make_httpx_mock(status_code: int, json_data: dict | None = None, raise_exc: Exception | None = None):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json = MagicMock(return_value=json_data or {})
    response.text = str(json_data)

    client = AsyncMock()
    if raise_exc:
        client.post = AsyncMock(side_effect=raise_exc)
    else:
        client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


# ---------------------------------------------------------------------------
# start_session
# ---------------------------------------------------------------------------

async def test_start_session_returns_session_id():
    mock = _make_httpx_mock(200, {
        "session_id": "abc-123",
        "started_at": "2026-01-01T00:00:00",
        "message": "Session initialized.",
    })
    with patch("guardian_client.httpx.AsyncClient", return_value=mock):
        result = await start_session("alice", "lab01", "EE101")
    assert result == "abc-123"


async def test_start_session_409_raises_guardian_error():
    mock = _make_httpx_mock(409, {"detail": "Session already exists."})
    with patch("guardian_client.httpx.AsyncClient", return_value=mock):
        with pytest.raises(GuardianError) as exc_info:
            await start_session("alice", "lab01", "EE101")
    assert exc_info.value.status_code == 409
    assert "Session already exists" in exc_info.value.detail


async def test_start_session_403_raises_guardian_error():
    mock = _make_httpx_mock(403, {"detail": "Forbidden."})
    with patch("guardian_client.httpx.AsyncClient", return_value=mock):
        with pytest.raises(GuardianError) as exc_info:
            await start_session("alice", "lab01", "EE101")
    assert exc_info.value.status_code == 403


async def test_start_session_503_raises_guardian_error():
    mock = _make_httpx_mock(503, {"detail": "Persistence layer unavailable."})
    with patch("guardian_client.httpx.AsyncClient", return_value=mock):
        with pytest.raises(GuardianError) as exc_info:
            await start_session("alice", "lab01", "EE101")
    assert exc_info.value.status_code == 503


async def test_start_session_network_error_raises_guardian_error():
    mock = _make_httpx_mock(0, raise_exc=httpx.ConnectError("connection refused"))
    with patch("guardian_client.httpx.AsyncClient", return_value=mock):
        with pytest.raises(GuardianError) as exc_info:
            await start_session("alice", "lab01", "EE101")
    assert exc_info.value.status_code == 0
    assert "Network error" in exc_info.value.detail


# ---------------------------------------------------------------------------
# end_session
# ---------------------------------------------------------------------------

async def test_end_session_returns_report_data():
    mock = _make_httpx_mock(200, {
        "session_id": "abc-123",
        "report_id": "rep-456",
        "ended_at": "2026-01-01T00:01:00",
        "summary": {"final_status": "CLEAN", "total_questions": 2},
    })
    with patch("guardian_client.httpx.AsyncClient", return_value=mock):
        result = await end_session("alice", "abc-123")
    assert result["report_id"] == "rep-456"
    assert result["summary"]["final_status"] == "CLEAN"


async def test_end_session_404_raises_guardian_error():
    mock = _make_httpx_mock(404, {"detail": "Session not found."})
    with patch("guardian_client.httpx.AsyncClient", return_value=mock):
        with pytest.raises(GuardianError) as exc_info:
            await end_session("alice", "nonexistent")
    assert exc_info.value.status_code == 404


async def test_end_session_403_raises_guardian_error():
    mock = _make_httpx_mock(403, {"detail": "Forbidden."})
    with patch("guardian_client.httpx.AsyncClient", return_value=mock):
        with pytest.raises(GuardianError) as exc_info:
            await end_session("alice", "abc-123")
    assert exc_info.value.status_code == 403


async def test_end_session_network_error_raises_guardian_error():
    mock = _make_httpx_mock(0, raise_exc=httpx.ConnectError("connection refused"))
    with patch("guardian_client.httpx.AsyncClient", return_value=mock):
        with pytest.raises(GuardianError) as exc_info:
            await end_session("alice", "abc-123")
    assert exc_info.value.status_code == 0
