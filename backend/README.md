# PhantomNet backend (Phase 2)

This service supplies the Phase 1 dashboard telemetry contract and isolated
honeypot interfaces. It binds to loopback by default. It records ingress
metadata and attacker inputs; it never runs captured commands, mounts a host
directory, or sends SQL to a database.

## Run

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m app
```

Set `NEXT_PUBLIC_WS_URL=ws://127.0.0.1:8000/ws/telemetry` and
`NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` in the frontend environment to
connect the existing dashboard.

## Interfaces

- OpenAPI documentation: `/docs`
- Health: `GET /api/health`
- Session intake: `POST /api/sessions`
- Captured network metadata: `POST /api/network/intercept`
- Captured commands: `POST /api/sessions/{session_id}/commands`
- Telemetry history: `GET /api/telemetry/events`
- Virtual filesystem: `/api/filesystem/{session_id}/{list,stat,read}`
- SQL honeypot intake: `POST /api/sql/query`
- Security status: `GET /api/security/status`
- Dashboard event stream: `GET /ws/telemetry`

The network endpoint is a safe event-ingress adapter, not a privileged packet
sniffer, SSH proxy, or firewall rule. Configure a separate, explicitly
authorized capture component to forward observed connection metadata.

FUSE operations are implemented for Linux with `pyfuse3`, but mounting is
explicit and is not performed automatically. The virtual filesystem only
exposes context-store records and cannot resolve paths against the host.

ChromaDB stores context under the configured persistence directory, scoped by
session. The Phase 2 LLM service intentionally reports unavailable; file and
SQL response generation returns HTTP 503 rather than fabricated content.

## Tests

From `backend`, run `python -m pytest -q`.
