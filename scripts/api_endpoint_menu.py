#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import http.cookiejar
import json
import os
import ssl
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

TARGETS = {
    "1": ("API Central local", "http://127.0.0.1:8003", "apicentral"),
    "2": ("API Central publica", "https://robio-ai.com/api", "apicentral"),
    "3": ("Dashboard local", "http://127.0.0.1:8010", "dashboard"),
}

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_ENV_FILES = (
    str(REPO_ROOT / "apicentral/.env"),
    str(REPO_ROOT / "dashboard/.env"),
    str(REPO_ROOT / "servicios/.env"),
)


@dataclass
class Endpoint:
    index: int
    method: str
    path: str
    summary: str
    tags: list[str]
    operation: dict[str, Any]

    @property
    def label(self) -> str:
        tag = ",".join(self.tags) if self.tags else "-"
        summary = f" - {self.summary}" if self.summary else ""
        return f"{self.index:03d}. {self.method.upper():6} {self.path} [{tag}]{summary}"


class HttpClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 20.0,
        insecure: bool = False,
        response_limit: int = 12000,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.response_limit = response_limit
        self.bearer_token = ""
        self.service_token = ""
        self.strip_api_prefix = False
        self.cookiejar = http.cookiejar.CookieJar()
        self.context = ssl._create_unverified_context() if insecure else None
        handlers: list[Any] = [urllib.request.HTTPCookieProcessor(self.cookiejar)]
        if self.context is not None:
            handlers.append(urllib.request.HTTPSHandler(context=self.context))
        self.opener = urllib.request.build_opener(*handlers)

    def url_for(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        if self.strip_api_prefix and path.startswith("/api/"):
            path = path[4:]
        parsed = urllib.parse.urlparse(self.base_url)
        origin = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
        base_path = parsed.path.rstrip("/")
        clean_path = "/" + path.lstrip("/")
        if base_path and clean_path.startswith(base_path + "/"):
            return origin + clean_path
        return origin + base_path + clean_path

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: Any = None,
        headers: dict[str, str] | None = None,
        use_auth: bool = True,
    ) -> tuple[int, dict[str, str], bytes]:
        url = self.url_for(path)
        if query:
            clean_query = {k: v for k, v in query.items() if v not in (None, "")}
            if clean_query:
                separator = "&" if urllib.parse.urlparse(url).query else "?"
                url += separator + urllib.parse.urlencode(clean_query, doseq=True)

        request_headers = {"Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        data: bytes | None = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=True).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        if use_auth:
            if self.bearer_token:
                request_headers["Authorization"] = f"Bearer {self.bearer_token}"
            if self.service_token:
                request_headers["X-Robiotec-Ingest-Token"] = self.service_token

        req = urllib.request.Request(url, data=data, headers=request_headers, method=method.upper())
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                return resp.status, dict(resp.headers.items()), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers.items()), exc.read()


def load_env_file(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path:
        return values
    candidate = Path(path)
    if not candidate.is_absolute() and not candidate.exists():
        repo_candidate = REPO_ROOT / path
        if repo_candidate.exists():
            candidate = repo_candidate
    try:
        lines = candidate.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_env_files(paths: tuple[str, ...] | list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for path in paths:
        # Preserve the first value found so apicentral/.env wins for shared keys.
        for key, value in load_env_file(path).items():
            values.setdefault(key, value)
    return values


def choose_target() -> tuple[str, str]:
    print("Selecciona destino:")
    for key, (label, url, _) in TARGETS.items():
        print(f"  {key}. {label} ({url})")
    print("  4. Personalizado")
    choice = input("> ").strip() or "1"
    if choice in TARGETS:
        _, url, kind = TARGETS[choice]
        return url, kind
    url = input("Base URL: ").strip()
    kind = input("Tipo [apicentral/dashboard/auto]: ").strip().lower() or "auto"
    return url, kind


def fetch_openapi(client: HttpClient, explicit_url: str = "") -> dict[str, Any]:
    candidates = [explicit_url] if explicit_url else ["/openapi.json", "/api/openapi.json"]
    last_error = ""
    for candidate in candidates:
        if not candidate:
            continue
        status, _, raw = client.request("GET", candidate, use_auth=False)
        if status == 200:
            try:
                return json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as exc:
                last_error = f"{candidate}: JSON invalido: {exc}"
        else:
            last_error = f"{candidate}: HTTP {status}"
    raise SystemExit(f"No pude leer OpenAPI. Ultimo error: {last_error}")


def detect_api_prefix_mode(client: HttpClient, schema: dict[str, Any]) -> None:
    paths = schema.get("paths") or {}
    if "/api/health" not in paths:
        return
    status_as_is, _, _ = client.request("GET", "/api/health", use_auth=False)
    if status_as_is == 200:
        return
    original = client.strip_api_prefix
    client.strip_api_prefix = True
    status_stripped, _, _ = client.request("GET", "/api/health", use_auth=False)
    if status_stripped == 200:
        return
    client.strip_api_prefix = original


def collect_endpoints(schema: dict[str, Any]) -> list[Endpoint]:
    endpoints: list[Endpoint] = []
    for path, methods in sorted((schema.get("paths") or {}).items()):
        if not isinstance(methods, dict):
            continue
        for method, operation in sorted(methods.items()):
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            endpoints.append(
                Endpoint(
                    index=len(endpoints) + 1,
                    method=method.lower(),
                    path=path,
                    summary=str(operation.get("summary") or operation.get("operationId") or ""),
                    tags=[str(tag) for tag in operation.get("tags") or []],
                    operation=operation,
                )
            )
    return endpoints


def try_login(client: HttpClient, kind: str, endpoints: list[Endpoint], username: str, password: str) -> bool:
    login_paths = [ep.path for ep in endpoints if ep.method == "post" and ep.path.endswith(("/auth/login", "/login"))]
    candidates: list[tuple[str, dict[str, str]]] = []
    for path in login_paths:
        if path.endswith("/api/login") or path == "/api/login":
            candidates.append((path, {"identity": username, "password": password}))
        elif path.endswith("/auth/login"):
            candidates.append((path, {"username": username, "password": password}))
    if kind == "dashboard":
        candidates.insert(0, ("/api/login", {"identity": username, "password": password}))
    else:
        candidates.insert(0, ("/auth/login", {"username": username, "password": password}))
        candidates.insert(1, ("/api/auth/login", {"username": username, "password": password}))

    seen: set[str] = set()
    for path, body in candidates:
        key = path + json.dumps(body, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        status, _, raw = client.request("POST", path, body=body, use_auth=False)
        if status < 300:
            payload = parse_json(raw)
            token = str(payload.get("access_token") or "")
            if token:
                client.bearer_token = token
            print(f"Login OK via {path}")
            return True
    print("Login fallido.")
    return False


def auto_auth(
    client: HttpClient,
    kind: str,
    endpoints: list[Endpoint],
    env: dict[str, str],
    args: argparse.Namespace,
    *,
    force_login: bool = False,
) -> bool:
    authenticated = False
    if args.token:
        client.bearer_token = args.token.strip()
        authenticated = True
    if args.service_token:
        client.service_token = args.service_token.strip()
    elif env.get("SERVICE_INGEST_TOKEN"):
        client.service_token = env["SERVICE_INGEST_TOKEN"]
    elif env.get("API_INGEST_TOKEN"):
        client.service_token = env["API_INGEST_TOKEN"]
    if client.service_token:
        authenticated = True

    if client.bearer_token and not force_login:
        return True

    if args.username:
        username = args.username
        password = args.password or getpass.getpass("Password: ")
        return try_login(client, kind, endpoints, username, password) or authenticated

    username = env.get("MASTER_USERNAME") or os.getenv("ROBIOTEC_USER") or ""
    password = env.get("MASTER_PASSWORD") or os.getenv("ROBIOTEC_PASSWORD") or ""
    if username and password:
        authenticated = try_login(client, kind, endpoints, username, password) or authenticated

    return authenticated


def auth_menu(client: HttpClient, kind: str, endpoints: list[Endpoint], env: dict[str, str], args: argparse.Namespace) -> None:
    if auto_auth(client, kind, endpoints, env, args):
        print("Auth automatica OK.")
        return

    while True:
        print("\nAutenticacion:")
        print("  1. Login usuario/password")
        print("  2. Pegar Bearer token")
        print("  3. Pegar service token (X-Robiotec-Ingest-Token)")
        print("  4. Continuar sin auth")
        choice = input("> ").strip() or "1"
        if choice == "1":
            default_user = env.get("MASTER_USERNAME") or os.getenv("ROBIOTEC_USER") or ""
            prompt = f"Usuario [{default_user}]: " if default_user else "Usuario: "
            username = input(prompt).strip() or default_user
            env_password = env.get("MASTER_PASSWORD") or os.getenv("ROBIOTEC_PASSWORD") or ""
            if env_password and input("Usar password del env? [s/N]: ").strip().lower() == "s":
                password = env_password
            else:
                password = getpass.getpass("Password: ")
            try_login(client, kind, endpoints, username, password)
            return
        if choice == "2":
            client.bearer_token = getpass.getpass("Bearer token: ").strip()
            return
        if choice == "3":
            client.service_token = getpass.getpass("Service token: ").strip()
            return
        if choice == "4":
            return


def parse_json(raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
        return payload if isinstance(payload, dict) else {"data": payload}
    except Exception:
        return {}


def resolve_ref(schema: Any, components: dict[str, Any]) -> Any:
    if not isinstance(schema, dict):
        return schema
    ref = schema.get("$ref")
    if not ref:
        return schema
    if not ref.startswith("#/components/schemas/"):
        return schema
    name = ref.rsplit("/", 1)[-1]
    return components.get("schemas", {}).get(name, schema)


def sample_from_schema(schema: Any, components: dict[str, Any], depth: int = 0) -> Any:
    if depth > 5:
        return None
    schema = resolve_ref(schema, components)
    if not isinstance(schema, dict):
        return None
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]
    if "anyOf" in schema:
        return sample_from_schema(schema["anyOf"][0], components, depth + 1)
    if "oneOf" in schema:
        return sample_from_schema(schema["oneOf"][0], components, depth + 1)
    schema_type = schema.get("type")
    if schema_type == "object" or "properties" in schema:
        props = schema.get("properties") or {}
        required = set(schema.get("required") or props.keys())
        return {
            key: sample_from_schema(value, components, depth + 1)
            for key, value in props.items()
            if key in required or depth == 0
        }
    if schema_type == "array":
        return [sample_from_schema(schema.get("items") or {}, components, depth + 1)]
    if schema_type == "integer":
        return 0
    if schema_type == "number":
        return 0.0
    if schema_type == "boolean":
        return True
    return "string"


def endpoint_body_sample(ep: Endpoint, schema: dict[str, Any]) -> Any:
    request_body = ep.operation.get("requestBody") or {}
    content = request_body.get("content") or {}
    media = content.get("application/json") or content.get("application/*+json") or {}
    if not media:
        return None
    return sample_from_schema(media.get("schema") or {}, schema.get("components") or {})


def prompt_parameters(ep: Endpoint) -> tuple[str, dict[str, Any]]:
    path = ep.path
    query: dict[str, Any] = {}
    params = ep.operation.get("parameters") or []
    for param in params:
        if not isinstance(param, dict):
            continue
        name = str(param.get("name") or "")
        location = str(param.get("in") or "")
        required = bool(param.get("required"))
        if location not in {"path", "query"} or not name:
            continue
        default = param.get("schema", {}).get("default")
        suffix = " requerido" if required else " opcional"
        prompt = f"{location} param '{name}' ({suffix}"
        if default is not None:
            prompt += f", default={default}"
        prompt += "): "
        value = input(prompt).strip()
        if not value and default is not None:
            value = str(default)
        if location == "path":
            if not value and required:
                value = input(f"Valor requerido para {name}: ").strip()
            path = path.replace("{" + name + "}", urllib.parse.quote(value, safe=""))
        elif value:
            query[name] = value
    return path, query


def prompt_body(ep: Endpoint, schema: dict[str, Any]) -> Any:
    if ep.method in {"get", "delete"}:
        return None
    sample = endpoint_body_sample(ep, schema)
    if sample is not None:
        print("\nEjemplo de body JSON:")
        print(json.dumps(sample, indent=2, ensure_ascii=True))
    print("Body JSON en una linea. Enter para omitir.")
    raw = input("> ").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"JSON invalido: {exc}")
        return prompt_body(ep, schema)


def print_response(status: int, headers: dict[str, str], raw: bytes, limit: int) -> None:
    content_type = headers.get("content-type") or headers.get("Content-Type") or ""
    print(f"\nHTTP {status} | {content_type}")
    text = raw.decode("utf-8", errors="replace")
    if "json" in content_type.lower():
        try:
            print(json.dumps(json.loads(text), indent=2, ensure_ascii=False)[:limit])
            return
        except Exception:
            pass
    print(text[:limit])
    if len(text) > limit:
        print(f"\n... respuesta truncada a {limit} caracteres")


def auth_missing(status: int, raw: bytes) -> bool:
    if status != 401:
        return False
    detail = str(parse_json(raw).get("detail") or parse_json(raw).get("message") or "").lower()
    return "not authenticated" in detail or "no autentic" in detail or "invalid" in detail or "token" in detail


def request_with_auto_reauth(
    client: HttpClient,
    method: str,
    path: str,
    *,
    endpoints: list[Endpoint],
    env: dict[str, str],
    args: argparse.Namespace,
    kind: str,
    query: dict[str, Any] | None = None,
    body: Any = None,
) -> tuple[int, dict[str, str], bytes]:
    status, headers, raw = client.request(method, path, query=query, body=body)
    if auth_missing(status, raw):
        print("401 de autenticacion; reintentando login automatico...")
        if auto_auth(client, kind, endpoints, env, args, force_login=True):
            status, headers, raw = client.request(method, path, query=query, body=body)
    return status, headers, raw


def parse_query_pairs(values: list[str]) -> dict[str, Any]:
    query: dict[str, Any] = {}
    for value in values:
        if "=" not in value:
            query[value] = ""
            continue
        key, raw = value.split("=", 1)
        if key in query:
            existing = query[key]
            if isinstance(existing, list):
                existing.append(raw)
            else:
                query[key] = [existing, raw]
        else:
            query[key] = raw
    return query


def parse_body_arg(raw: str) -> Any:
    if not raw:
        return None
    if raw.startswith("@"):
        with open(raw[1:], "r", encoding="utf-8") as fh:
            raw = fh.read()
    return json.loads(raw)


def execute_endpoint(
    client: HttpClient,
    ep: Endpoint,
    schema: dict[str, Any],
    *,
    endpoints: list[Endpoint],
    env: dict[str, str],
    args: argparse.Namespace,
    kind: str,
) -> None:
    print("\n" + ep.label)
    desc = str(ep.operation.get("description") or "").strip()
    if desc:
        print(textwrap.shorten(desc.replace("\n", " "), width=240))
    path, query = prompt_parameters(ep)
    body = prompt_body(ep, schema)
    status, headers, raw = request_with_auto_reauth(
        client,
        ep.method,
        path,
        endpoints=endpoints,
        env=env,
        args=args,
        kind=kind,
        query=query,
        body=body,
    )
    print_response(status, headers, raw, client.response_limit)


def execute_direct(
    client: HttpClient,
    *,
    method: str,
    endpoint: str,
    endpoints: list[Endpoint],
    env: dict[str, str],
    args: argparse.Namespace,
    kind: str,
    query: dict[str, Any] | None = None,
    body: Any = None,
) -> None:
    status, headers, raw = request_with_auto_reauth(
        client,
        method,
        endpoint,
        endpoints=endpoints,
        env=env,
        args=args,
        kind=kind,
        query=query,
        body=body,
    )
    print_response(status, headers, raw, client.response_limit)


def print_endpoint_list(endpoints: list[Endpoint], search: str = "") -> None:
    needle = search.lower().strip()
    shown = 0
    for ep in endpoints:
        blob = f"{ep.method} {ep.path} {ep.summary} {' '.join(ep.tags)}".lower()
        if needle and needle not in blob:
            continue
        print(ep.label)
        shown += 1
    print(f"\n{shown} endpoint(s).")


def interactive_loop(
    client: HttpClient,
    endpoints: list[Endpoint],
    schema: dict[str, Any],
    env: dict[str, str],
    args: argparse.Namespace,
    kind: str,
) -> None:
    search = ""
    by_index = {ep.index: ep for ep in endpoints}
    while True:
        print("\nComandos: numero=consultar | /path o URL=GET directo | l=listar | s=buscar | a=auth | q=salir")
        cmd = input("> ").strip()
        if cmd.lower() in {"q", "quit", "salir"}:
            return
        if cmd.lower() in {"l", "listar", ""}:
            print_endpoint_list(endpoints, search)
            continue
        if cmd.lower() in {"s", "buscar"}:
            search = input("Buscar metodo/path/tag/texto (vacio limpia): ").strip()
            print_endpoint_list(endpoints, search)
            continue
        if cmd.lower() in {"a", "auth"}:
            auth_menu(client, kind, endpoints, env, args)
            continue
        if cmd.startswith("/") or cmd.startswith(("http://", "https://")):
            method = input("Metodo [GET]: ").strip().upper() or "GET"
            body = None
            if method.lower() not in {"get", "delete"}:
                raw_body = input("Body JSON en una linea o Enter para omitir: ").strip()
                if raw_body:
                    try:
                        body = json.loads(raw_body)
                    except json.JSONDecodeError as exc:
                        print(f"JSON invalido: {exc}")
                        continue
            execute_direct(
                client,
                method=method,
                endpoint=cmd,
                endpoints=endpoints,
                env=env,
                args=args,
                kind=kind,
                body=body,
            )
            continue
        try:
            index = int(cmd)
        except ValueError:
            print("Comando no reconocido.")
            continue
        ep = by_index.get(index)
        if not ep:
            print("Endpoint no existe.")
            continue
        execute_endpoint(client, ep, schema, endpoints=endpoints, env=env, args=args, kind=kind)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Menu interactivo para consultar endpoints FastAPI/OpenAPI.")
    parser.add_argument("--base-url", help="Base URL. Ej: http://127.0.0.1:8003 o https://robio-ai.com/api")
    parser.add_argument("--kind", choices=["apicentral", "dashboard", "auto"], default="auto")
    parser.add_argument("--openapi-url", default="", help="OpenAPI URL/ruta si no es /openapi.json")
    parser.add_argument("--env-file", default="", help="Archivo .env para leer defaults/tokens")
    parser.add_argument("--username", default="", help="Usuario para login automatico")
    parser.add_argument("--password", default="", help="Password para login automatico")
    parser.add_argument("--token", default="", help="Bearer token existente")
    parser.add_argument("--service-token", default="", help="Token X-Robiotec-Ingest-Token")
    parser.add_argument("--manual-auth", action="store_true", help="Preguntar login/token en vez de autenticar automaticamente")
    parser.add_argument("--no-auth", action="store_true", help="No configurar tokens automaticamente")
    parser.add_argument("--endpoint", default="", help="Endpoint o URL para consultar directamente")
    parser.add_argument("--method", default="GET", help="Metodo para --endpoint")
    parser.add_argument("--query", action="append", default=[], help="Query param para --endpoint. Ej: a=1")
    parser.add_argument("--body", default="", help="JSON para --endpoint, o @archivo.json")
    parser.add_argument("--insecure", action="store_true", help="No validar TLS")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--response-limit", type=int, default=12000)
    parser.add_argument("--list", action="store_true", help="Listar endpoints y salir")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = args.base_url
    kind = args.kind
    if not base_url:
        base_url, selected_kind = choose_target()
        if kind == "auto":
            kind = selected_kind

    env = load_env_file(args.env_file) if args.env_file else load_env_files(DEFAULT_ENV_FILES)
    client = HttpClient(
        base_url,
        timeout=args.timeout,
        insecure=args.insecure,
        response_limit=args.response_limit,
    )
    schema = fetch_openapi(client, args.openapi_url)
    detect_api_prefix_mode(client, schema)
    endpoints = collect_endpoints(schema)
    if not endpoints:
        raise SystemExit("OpenAPI no trajo endpoints.")

    print(f"\nOpenAPI: {schema.get('title', 'sin titulo')} | endpoints: {len(endpoints)}")
    print(f"Base efectiva: {client.base_url} | strip_api_prefix={client.strip_api_prefix}")

    if args.list:
        print_endpoint_list(endpoints)
        return 0

    if not args.no_auth:
        if args.manual_auth:
            auth_menu(client, kind, endpoints, env, args)
        elif auto_auth(client, kind, endpoints, env, args):
            print("Auth automatica OK.")
        else:
            print("Auth automatica no encontro credenciales/tokens; continuando sin auth.")

    if args.endpoint:
        execute_direct(
            client,
            method=args.method,
            endpoint=args.endpoint,
            endpoints=endpoints,
            env=env,
            args=args,
            kind=kind,
            query=parse_query_pairs(args.query),
            body=parse_body_arg(args.body),
        )
        return 0

    print_endpoint_list(endpoints)
    interactive_loop(client, endpoints, schema, env, args, kind)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
