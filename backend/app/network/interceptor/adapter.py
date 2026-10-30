from dataclasses import dataclass
from ipaddress import ip_address
from typing import Literal


SUPPORTED_PROTOCOLS = {"ssh", "postgresql", "mysql"}


@dataclass(frozen=True)
class CapturedConnection:
    source_ip: str
    source_port: int | None
    destination: str | None
    destination_port: int
    protocol: Literal["ssh", "postgresql", "mysql"]


def normalize_connection(
    source_ip: str,
    source_port: int | None,
    destination: str | None,
    destination_port: int,
    protocol: str,
) -> CapturedConnection:
    source = str(ip_address(source_ip))
    if destination:
        destination = str(ip_address(destination))
    normalized_protocol = protocol.casefold()
    if normalized_protocol not in SUPPORTED_PROTOCOLS:
        raise ValueError("Only SSH, PostgreSQL, and MySQL ingress are supported.")
    return CapturedConnection(
        source_ip=source,
        source_port=source_port,
        destination=destination,
        destination_port=destination_port,
        protocol=normalized_protocol,  # type: ignore[arg-type]
    )
