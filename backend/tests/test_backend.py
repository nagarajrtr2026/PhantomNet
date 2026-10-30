import pytest
from pydantic import ValidationError

from app.events import HackerCommandEvent, event_payload
from app.filesystem.virtual_fs import InvalidVirtualPath, normalize_virtual_path
from app.sessions.manager import SessionManager


def test_health_and_security_status(client):
    assert client.get("/api/health").json()["status"] == "ok"
    status = client.get("/api/security/status").json()
    assert status["host_command_execution"] is False
    assert status["host_filesystem_access"] is False
    assert status["production_database_connections"] is False


def test_capture_creates_isolated_session_and_dashboard_events(client):
    response = client.post(
        "/api/network/intercept",
        json={
            "source_ip": "192.0.2.10",
            "source_port": 50123,
            "destination": "192.0.2.20",
            "destination_port": 22,
            "protocol": "ssh",
        },
    )
    assert response.status_code == 202
    session_id = response.json()["session"]["session_id"]
    events = client.get("/api/telemetry/events").json()
    assert [event["type"] for event in events] == ["session_update", "network_event"]
    assert all(event["sessionId"] == session_id for event in events)
    assert events[0]["sourceIp"] == "192.0.2.10"


def test_capture_command_never_executes_and_reports_phase_boundary(client):
    session = client.post(
        "/api/sessions",
        json={"source_ip": "198.51.100.8", "protocol": "ssh"},
    ).json()
    response = client.post(
        f"/api/sessions/{session['session_id']}/commands",
        json={"command": "id; whoami"},
    )
    assert response.status_code == 503
    events = client.get("/api/telemetry/events").json()
    assert any(event["type"] == "hacker_command" for event in events)
    assert any(
        event["type"] == "llm_response" and event["status"] == "error"
        for event in events
    )


def test_sql_is_captured_but_never_executed(client):
    session = client.post(
        "/api/sessions",
        json={"source_ip": "203.0.113.11", "protocol": "postgresql"},
    ).json()
    response = client.post(
        "/api/sql/query",
        json={
            "session_id": session["session_id"],
            "query": "SELECT * FROM employees",
            "database": "company",
        },
    )
    assert response.status_code == 503
    events = client.get("/api/sql/activity").json()
    assert events[-1]["query"] == "SELECT * FROM employees"


def test_sql_sensitive_capability_probe_is_logged(client):
    session = client.post(
        "/api/sessions",
        json={"source_ip": "203.0.113.12", "protocol": "postgresql"},
    ).json()
    response = client.post(
        "/api/sql/query",
        json={
            "session_id": session["session_id"],
            "query": "SELECT pg_read_file('/etc/passwd')",
        },
    )
    assert response.status_code == 503
    assert any(
        event["type"] == "security_event"
        for event in client.get("/api/telemetry/events").json()
    )


def test_sql_query_validation_and_schema_extraction(client):
    engine = client.app.state.services.dynamic_sql
    assert engine.extract_schema("SELECT * FROM public.users") == ["public.users"]
    with pytest.raises(ValueError):
        engine.normalize("\x00select 1")
    with pytest.raises(ValueError):
        engine.normalize("x" * 16385)


def test_filesystem_activity_rejects_traversal(client):
    session = client.post(
        "/api/sessions",
        json={"source_ip": "203.0.113.13", "protocol": "ssh"},
    ).json()
    response = client.get(
        f"/api/filesystem/{session['session_id']}/read",
        params={"path": "../etc/passwd"},
    )
    assert response.status_code == 400
    assert client.get("/api/filesystem/activity").json()[-1]["action"] == "read"
    assert any(
        event["type"] == "security_event"
        for event in client.get("/api/telemetry/events").json()
    )


def test_event_schema_matches_dashboard_camel_case():
    event = HackerCommandEvent(
        type="hacker_command",
        sessionId="session-1",
        command="uname -a",
        source="192.0.2.1",
    )
    payload = event_payload(event)
    assert payload["sessionId"] == "session-1"
    assert payload["type"] == "hacker_command"
    with pytest.raises(ValidationError):
        HackerCommandEvent(type="hacker_command", command="")


def test_virtual_paths_are_confined():
    assert normalize_virtual_path("etc/hosts") == "etc/hosts"
    for path in ("../etc/passwd", "safe/../../host", "/etc/passwd", r"etc\hosts"):
        with pytest.raises(InvalidVirtualPath):
            normalize_virtual_path(path)


def test_session_manager_tracks_event_references():
    manager = SessionManager()
    session = manager.create("192.0.2.3", "ssh", 2200)
    updated = manager.record_event(session.session_id, "event-1")
    assert updated.event_ids == ["event-1"]
    assert updated.last_activity >= session.last_activity


def test_ended_session_rejects_new_attacker_input(client):
    session = client.post(
        "/api/sessions",
        json={"source_ip": "198.51.100.40", "protocol": "ssh"},
    ).json()
    session_id = session["session_id"]
    assert client.post(f"/api/sessions/{session_id}/end").status_code == 200
    response = client.post(
        f"/api/sessions/{session_id}/commands", json={"command": "ls"}
    )
    assert response.status_code == 409


def test_chroma_context_is_session_scoped(client):
    context = client.app.state.services.context
    context.remember("session-a", "sql_context", "schema", "table customers")
    context.remember("session-b", "sql_context", "schema", "table accounts")
    assert context.get("session-a", "sql_context", "schema")["document"] == "table customers"
    assert context.search("session-a", "customers", kind="sql_context", limit=5) == [
        "table customers"
    ]


def test_virtual_file_reads_persist_per_session(client):
    context = client.app.state.services.context
    session = client.post(
        "/api/sessions",
        json={"source_ip": "198.51.100.41", "protocol": "ssh"},
    ).json()
    session_id = session["session_id"]
    context.remember(
        session_id,
        "filesystem_node",
        "reports/q1.txt",
        "session A report",
        is_directory=False,
        generated=True,
    )
    response = client.get(
        f"/api/filesystem/{session_id}/read", params={"path": "reports/q1.txt"}
    )
    assert response.json()["content"] == "session A report"
    assert context.get("session-b", "filesystem_node", "reports/q1.txt") is None


def test_virtual_root_metadata_and_directory_listing(client):
    session = client.post(
        "/api/sessions",
        json={"source_ip": "198.51.100.42", "protocol": "ssh"},
    ).json()
    session_id = session["session_id"]
    assert client.get(f"/api/filesystem/{session_id}/stat").json()["type"] == "directory"
    assert client.get(f"/api/filesystem/{session_id}/list").json()["entries"] == []


def test_websocket_delivers_real_published_events(client):
    with client.websocket_connect("/ws/telemetry") as websocket:
        session = client.post(
            "/api/sessions",
            json={"source_ip": "192.0.2.30", "protocol": "ssh"},
        ).json()
        delivered = websocket.receive_json()
        assert delivered["type"] == "session_update"
        assert delivered["sessionId"] == session["session_id"]
