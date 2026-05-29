from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def build_crdb_dsn(url: str, ssl_root_cert: str) -> str:
    """Build a CockroachDB DSN from URL and SSL cert path.

    Appends sslrootcert if cert file exists; warns and downgrades
    sslmode=verify-full to sslmode=require if cert file is missing;
    falls back to sslmode=require if no sslmode is specified.
    """
    ok, _ = validate_crdb_url(url)
    if not ok:
        return ""
    if not url:
        return ""
    cert = ssl_root_cert
    if cert and Path(cert).exists() and "sslrootcert=" not in url:
        sep = "&" if "?" in url else "?"
        cert_path = cert.replace("\\", "/")
        url = f"{url}{sep}sslrootcert={cert_path}"
    elif "sslrootcert=" not in url:
        if "sslmode=verify-full" in url:
            if not cert or not Path(cert).exists():
                import logging
                logger = logging.getLogger("potato.bootstrap")
                if not logger.handlers or logger.isEnabledFor(logging.WARNING):
                    logger.warning(
                        "CRDB SSL cert file not found at '%s', downgrading sslmode=verify-full to sslmode=require. "
                        "Set CRDB_SSL_ROOT_CERT to a valid path for full certificate verification.",
                        cert,
                    )
                url = url.replace("sslmode=verify-full", "sslmode=require")
        elif "sslmode=" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}sslmode=require"
    return url


@dataclass(frozen=True)
class BootstrapSettings:
    crdb_url: str
    crdb_ssl_root_cert: str

    @property
    def crdb_dsn(self) -> str:
        return build_crdb_dsn(self.crdb_url, self.crdb_ssl_root_cert)


def validate_crdb_url(url: str) -> tuple[bool, str]:
    u = (url or "").strip()
    if not u:
        return False, "CRDB_DATABASE_URL \u672a\u8bbe\u7f6e"
    lower = u.lower()
    if lower.startswith("postgresql://") or lower.startswith("postgres://"):
        return True, ""
    if "mkdir" in lower or "invoke-webrequest" in lower or "curl " in lower or "cert" in lower and "cockroachlabs.cloud/clusters" in lower:
        return (
            False,
            "CRDB_DATABASE_URL \u586b\u9519\u4e86\uff1a\u4f60\u628a\u300c\u4e0b\u8f7d\u8bc1\u4e66\u547d\u4ee4\u300d\u7c98\u8fdb\u53bb\u4e86\u3002"
            "\u53ea\u80fd\u586b Cockroach Connect \u91cc\u7684 postgresql:// \u8fde\u63a5\u4e32\uff1b\u8bc1\u4e66\u7531 CRDB_CLUSTER_ID \u81ea\u52a8\u4e0b\u8f7d",
        )
    return False, f"CRDB_DATABASE_URL \u5fc5\u987b\u4ee5 postgresql:// \u5f00\u5934\uff0c\u5f53\u524d\u5f00\u5934: {u[:40]!r}..."


def load_bootstrap_settings() -> BootstrapSettings:
    cert = os.getenv("CRDB_SSL_ROOT_CERT", "")
    if not cert:
        default_cert = Path(os.getenv("APPDATA", "")) / "postgresql" / "root.crt"
        if default_cert.exists():
            cert = str(default_cert)
    if not cert:
        cert = "/data/postgresql/root.crt"
    return BootstrapSettings(
        crdb_url=os.getenv("CRDB_DATABASE_URL", ""),
        crdb_ssl_root_cert=cert,
    )
