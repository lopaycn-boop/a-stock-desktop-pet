from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import zipfile
from pathlib import Path
from typing import Any

import httpx

ZEABUR_GRAPHQL = "https://api.zeabur.com/graphql"
ZEABUR_UPLOAD = "https://api.zeabur.com/v2/upload"


class ZeaburClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(ZEABUR_GRAPHQL, headers=self.headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        if data.get("errors"):
            raise RuntimeError(json.dumps(data["errors"], ensure_ascii=False))
        return data.get("data") or {}

    def me(self) -> dict[str, Any]:
        data = self._graphql("query { me { _id username email } }")
        return data.get("me") or {}

    def list_projects(self, *, include_services: bool = True) -> list[dict[str, Any]]:
        query_with_services = """
            query {
              projects {
                edges {
                  node {
                    _id
                    name
                    environments { _id name }
                    services {
                      edges {
                        node {
                          _id
                          name
                          status
                        }
                      }
                    }
                  }
                }
              }
            }
            """
        query_basic = """
            query {
              projects {
                edges {
                  node {
                    _id
                    name
                    environments { _id name }
                  }
                }
              }
            }
            """
        if include_services:
            try:
                data = self._graphql(query_with_services)
            except RuntimeError:
                data = self._graphql(query_basic)
        else:
            data = self._graphql(query_basic)
        edges = (data.get("projects") or {}).get("edges") or []
        return [e["node"] for e in edges if e.get("node")]

    @staticmethod
    def _normalize_id(value: str) -> str:
        value = (value or "").strip()
        for prefix in ("service-", "project-", "environment-"):
            if value.startswith(prefix):
                return value[len(prefix) :]
        return value

    def find_service(
        self,
        *,
        project_name: str | None = None,
        service_name: str | None = None,
        service_id: str | None = None,
    ) -> dict[str, Any] | None:
        target_service_id = self._normalize_id(service_id or "")
        for project in self.list_projects():
            if project_name and project.get("name") != project_name:
                continue
            envs = project.get("environments") or []
            environment_id = ""
            for env in envs:
                if env.get("name", "").lower() in {"production", "prod"}:
                    environment_id = env.get("_id", "")
                    break
            if not environment_id and envs:
                environment_id = envs[0].get("_id", "")

            service_edges = ((project.get("services") or {}).get("edges") or [])
            for edge in service_edges:
                node = edge.get("node") or {}
                sid = node.get("_id", "")
                if target_service_id and self._normalize_id(sid) != target_service_id:
                    continue
                if service_name and node.get("name") != service_name:
                    continue
                return {
                    "project_id": project.get("_id"),
                    "project_name": project.get("name"),
                    "environment_id": environment_id,
                    "service_id": sid,
                    "service_name": node.get("name"),
                    "status": node.get("status"),
                }
        return None

    def redeploy_service(self, service_id: str, environment_id: str) -> bool:
        data = self._graphql(
            """
            mutation Redeploy($serviceID: ObjectID!, $environmentID: ObjectID!) {
              redeployService(serviceID: $serviceID, environmentID: $environmentID)
            }
            """,
            {"serviceID": service_id, "environmentID": environment_id},
        )
        return bool(data.get("redeployService"))

    def restart_service(self, service_id: str, environment_id: str) -> bool:
        data = self._graphql(
            """
            mutation Restart($serviceID: ObjectID!, $environmentID: ObjectID!) {
              restartService(serviceID: $serviceID, environmentID: $environmentID)
            }
            """,
            {"serviceID": service_id, "environmentID": environment_id},
        )
        return bool(data.get("restartService"))

    @staticmethod
    def _zip_project(root: Path) -> bytes:
        skip_dirs = {".git", ".venv", "__pycache__", "data", "node_modules"}
        skip_files = {".env", ".secrets.local.json", ".zeabur-build.env", "zbpack.json"}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in root.rglob("*"):
                if path.is_dir():
                    continue
                rel = path.relative_to(root)
                parts = set(rel.parts)
                if parts & skip_dirs:
                    continue
                if rel.name in skip_files or rel.suffix in {".db", ".pyc"}:
                    continue
                zf.write(path, rel.as_posix())
        return buf.getvalue()

    @staticmethod
    def _content_hash_zip(data: bytes) -> tuple[int, str]:
        digest = hashlib.sha256(data).digest()
        return len(data), base64.b64encode(digest).decode("ascii")

    def deploy_zip(
        self,
        project_root: Path,
        *,
        upload_type: str = "new_project",
        service_id: str | None = None,
        environment_id: str | None = None,
    ) -> dict[str, Any]:
        zip_bytes = self._zip_project(project_root)
        content_length, content_hash = self._content_hash_zip(zip_bytes)

        with httpx.Client(timeout=120.0) as client:
            stage = client.post(
                ZEABUR_UPLOAD,
                headers=self.headers,
                json={
                    "content_hash": content_hash,
                    "content_hash_algorithm": "sha256",
                    "content_length": content_length,
                },
            )
            stage.raise_for_status()
            stage_data = stage.json()

            presign_url = stage_data["presign_url"]
            presign_method = stage_data.get("presign_method", "PUT")
            presign_headers = stage_data.get("presign_header") or {"Content-Type": "application/zip"}
            upload_id = stage_data["upload_id"]

            upload_resp = client.request(presign_method, presign_url, headers=presign_headers, content=zip_bytes)
            upload_resp.raise_for_status()

            body: dict[str, Any] = {"upload_type": upload_type}
            if upload_type == "existing_service":
                body["service_id"] = service_id
                body["environment_id"] = environment_id

            prepare = client.post(
                f"{ZEABUR_UPLOAD}/{upload_id}/prepare",
                headers=self.headers,
                json=body,
            )
            prepare.raise_for_status()
            return prepare.json()


def finish_deploy(
    api_key: str,
    *,
    project_name: str | None = None,
    service_name: str | None = None,
    service_id: str | None = None,
    environment_id: str | None = None,
    upload_code: bool = True,
) -> dict[str, Any]:
    """Push ZIP to an existing Zeabur service, then redeploy."""
    client = ZeaburClient(api_key)
    root = Path(__file__).resolve().parents[1]
    result: dict[str, Any] = {"me": client.me()}

    sid = client._normalize_id(service_id or "")
    eid = client._normalize_id(environment_id or "")

    target = None
    if not sid or not eid:
        target = client.find_service(
            project_name=project_name,
            service_name=service_name,
            service_id=service_id,
        )
        sid = sid or client._normalize_id((target or {}).get("service_id", ""))
        eid = eid or client._normalize_id((target or {}).get("environment_id", ""))

    if not sid or not eid:
        raise ValueError(
            "Could not resolve service/environment IDs. "
            "Set ZEABUR_SERVICE_ID and ZEABUR_ENVIRONMENT_ID or pass project/service names."
        )

    result["target"] = target or {"service_id": sid, "environment_id": eid}

    if upload_code:
        upload = client.deploy_zip(
            root,
            upload_type="existing_service",
            service_id=sid,
            environment_id=eid,
        )
        result["action"] = "upload_existing_service"
        result["upload"] = upload

    ok = client.redeploy_service(sid, eid)
    result["redeploy_ok"] = ok
    result["ok"] = ok
    result["service_id"] = sid
    result["environment_id"] = eid
    result["dashboard_hint"] = f"https://zeabur.com/projects/{result['target'].get('project_id', '')}/services/{sid}"
    return result


def deploy_from_settings(settings) -> dict[str, Any]:
    api_key = settings.zeabur_api_key
    if not api_key:
        raise ValueError("ZEABUR_API_KEY not configured")

    client = ZeaburClient(api_key)
    root = Path(__file__).resolve().parents[1]
    result: dict[str, Any] = {"me": client.me()}

    service_id = client._normalize_id(settings.zeabur_service_id)
    environment_id = client._normalize_id(settings.zeabur_environment_id)

    if service_id and environment_id:
        ok = client.redeploy_service(service_id, environment_id)
        result["action"] = "redeploy"
        result["ok"] = ok
        result["service_id"] = service_id
        result["environment_id"] = environment_id
        return result

    upload = client.deploy_zip(root, upload_type="new_project")
    result["action"] = "upload_new_project"
    result["ok"] = True
    result["upload"] = upload
    if upload.get("url"):
        result["dashboard_url"] = upload["url"]
    return result
