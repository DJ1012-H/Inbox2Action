from __future__ import annotations

import asyncio
import json
from urllib.parse import unquote, urlsplit

from inbox2action.stage6.approval import ApprovalService, ApprovalServiceError

MAX_REQUEST_BODY = 1_000_000


async def serve_approval_ui(
    service: ApprovalService,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> None:
    """Serve the internal approval page with only Python's standard library."""

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await _handle_client(reader, writer, service)

    server = await asyncio.start_server(handler, host, port)
    async with server:
        await server.serve_forever()


async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    service: ApprovalService,
) -> None:
    try:
        request_line = await reader.readline()
        if not request_line:
            return
        method, target, _ = request_line.decode("ascii", errors="replace").split()
        headers: dict[str, str] = {}
        while True:
            line = await reader.readline()
            if line in {b"\r\n", b"\n", b""}:
                break
            name, value = line.decode("iso-8859-1").split(":", 1)
            headers[name.casefold()] = value.strip()
        body = b""
        if method == "POST":
            length = int(headers.get("content-length", "0"))
            if length < 0 or length > MAX_REQUEST_BODY:
                raise ApprovalServiceError("request_too_large")
            body = await reader.readexactly(length)
    except ApprovalServiceError as exc:
        status, content_type, payload = _approval_error_response(exc)
    except (ValueError, UnicodeError, asyncio.IncompleteReadError):
        status, content_type, payload = _invalid_request_response()
    else:
        try:
            status, content_type, payload = await _route(
                service, method, target, body
            )
        except ApprovalServiceError as exc:
            status, content_type, payload = _approval_error_response(exc)
        except Exception:  # noqa: BLE001 - server never exposes internal details
            status, content_type, payload = _server_error_response()
    writer.write(
        (
            f"HTTP/1.1 {status} {_reason(status)}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(payload)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        + payload
    )
    await writer.drain()
    writer.close()
    await writer.wait_closed()


def _approval_error_response(
    exc: ApprovalServiceError,
) -> tuple[int, str, bytes]:
    status = {
        "workflow_not_found": 404,
        "not_found": 404,
        "stale_action": 409,
        "stale_approval": 409,
        "workflow_not_waiting": 409,
    }.get(exc.code, 400)
    return (
        status,
        "application/json; charset=utf-8",
        json.dumps({"error": exc.code}).encode(),
    )


def _invalid_request_response() -> tuple[int, str, bytes]:
    return (
        400,
        "application/json; charset=utf-8",
        b'{"error":"invalid_request"}',
    )


def _server_error_response() -> tuple[int, str, bytes]:
    return 500, "application/json; charset=utf-8", b'{"error":"server_error"}'


async def _route(
    service: ApprovalService,
    method: str,
    target: str,
    body: bytes,
) -> tuple[int, str, bytes]:
    path = urlsplit(target).path
    if method == "GET" and path == "/":
        return 200, "text/html; charset=utf-8", render_approval_page().encode("utf-8")
    if method == "GET" and path == "/api/workflows":
        return _json_response(200, await service.list_pending())
    if path.startswith("/api/workflows/"):
        segments = [unquote(item) for item in path.split("/") if item]
        if len(segments) == 3 and method == "GET":
            return _json_response(200, await service.get_workflow(segments[2]))
        if len(segments) == 4 and method == "POST":
            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ApprovalServiceError("invalid_json") from exc
            if not isinstance(payload, dict):
                raise ApprovalServiceError("invalid_json")
            operation = segments[3]
            if operation not in {"approve", "reject", "edit", "clarify"}:
                raise ApprovalServiceError("unknown_operation")
            expected_revision = payload.get("expected_revision")
            action_id = payload.get("action_id")
            parameters = payload.get("parameters")
            if not isinstance(expected_revision, int) or isinstance(
                expected_revision, bool
            ):
                raise ApprovalServiceError("invalid_approval")
            if not isinstance(action_id, str) or not action_id:
                raise ApprovalServiceError("invalid_approval")
            if parameters is not None and not isinstance(parameters, dict):
                raise ApprovalServiceError("invalid_approval")
            result = await service.decide(
                segments[2],
                operation=operation,  # type: ignore[arg-type]
                expected_revision=expected_revision,
                action_id=action_id,
                parameters=parameters,
            )
            return _json_response(200, result)
    raise ApprovalServiceError("not_found")


def render_approval_page() -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Inbox2Action Approval</title>
<style>body{font-family:system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem}button{margin:.25rem}pre{white-space:pre-wrap;background:#f5f5f5;padding:1rem}li{margin:.5rem 0}</style>
</head><body><h1>Inbox2Action approval</h1>
<p>This local page only resumes the existing LangGraph approval interrupt. No provider write is enabled in Stage 6.</p>
<section><h2>Pending workflows</h2><ul id="list"></ul></section>
<section><h2>Workflow detail</h2><pre id="detail">Select a workflow.</pre>
<button id="approve" disabled>Approve</button><button id="reject" disabled>Reject</button>
<button id="edit" disabled>Edit JSON</button><button id="clarify" disabled>Clarify JSON</button></section>
<script>
let current=null;
const list=document.getElementById('list'), detail=document.getElementById('detail');
async function load(){const r=await fetch('/api/workflows');const items=await r.json();list.textContent='';items.forEach(item=>{const b=document.createElement('button');b.textContent=item.email.subject+' ['+item.thread_id+']';b.onclick=()=>show(item.thread_id);const li=document.createElement('li');li.appendChild(b);list.appendChild(li)});}
async function show(id){const r=await fetch('/api/workflows/'+encodeURIComponent(id));current=await r.json();detail.textContent=JSON.stringify(current,null,2);['approve','reject','edit','clarify'].forEach(x=>document.getElementById(x).disabled=false)}
async function act(op,parameters){if(!current)return;const body={action_id:current.current_action_id,expected_revision:current.approval_revision};if(parameters)body.parameters=parameters;const r=await fetch('/api/workflows/'+encodeURIComponent(current.thread_id)+'/'+op,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});const data=await r.json();if(!r.ok){alert(data.error||'approval failed');return}current=data;detail.textContent=JSON.stringify(data,null,2);load()}
document.getElementById('approve').onclick=()=>act('approve');document.getElementById('reject').onclick=()=>act('reject');
document.getElementById('edit').onclick=()=>{const raw=prompt('Replacement parameters as JSON');if(raw)try{act('edit',JSON.parse(raw))}catch(e){alert('invalid JSON')}};
document.getElementById('clarify').onclick=()=>{const raw=prompt('Clarified parameters as JSON');if(raw)try{act('clarify',JSON.parse(raw))}catch(e){alert('invalid JSON')}};
load();
</script></body></html>"""


def _json_response(status: int, value: object) -> tuple[int, str, bytes]:
    return status, "application/json; charset=utf-8", json.dumps(
        value, ensure_ascii=False
    ).encode("utf-8")


def _reason(status: int) -> str:
    return {200: "OK", 400: "Bad Request", 500: "Internal Server Error"}.get(
        status, "Error"
    )
