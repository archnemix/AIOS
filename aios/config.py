"""Configuration for the local inference gateway."""

import ipaddress
import os
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Config:
    token: str
    host: str = "127.0.0.1"
    port: int = 8080
    backend: str = "http://127.0.0.1:8081"
    max_body_bytes: int = 2 * 1024 * 1024
    timeout: int = 300

    @classmethod
    def from_env(cls):
        token = os.environ.get("AIOS_API_TOKEN", "")
        if len(token) < 32:
            raise ValueError("AIOS_API_TOKEN must contain at least 32 characters")
        host = os.environ.get("AIOS_HOST", "127.0.0.1")
        port = int(os.environ.get("AIOS_PORT", "8080"))
        backend = os.environ.get("AIOS_BACKEND", "http://127.0.0.1:8081").rstrip("/")
        parsed = urlsplit(backend)
        try:
            loopback = ipaddress.ip_address(parsed.hostname or "").is_loopback
            backend_port = parsed.port
        except ValueError:
            loopback = False
            backend_port = None
        if (parsed.scheme != "http" or not loopback or not backend_port
                or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise ValueError("AIOS_BACKEND must be a loopback HTTP origin with an explicit port")
        if not 1 <= port <= 65535:
            raise ValueError("AIOS_PORT must be between 1 and 65535")
        return cls(token=token, host=host, port=port, backend=backend)
