"""Python-managed SSL certificate utilities for the backend server."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


CERT_COMMON_NAME = "bgpx.net"
CERT_FILE_NAME = "bgpx.net.crt"
KEY_FILE_NAME = "bgpx.net.key"
KEY_SIZE_BITS = 4094
VALIDITY_YEARS = 10


@dataclass(frozen=True)
class SSLFiles:
    """Resolved SSL certificate and private-key file paths."""

    cert_file: Path
    key_file: Path


def default_ssl_cert_dir() -> Path:
    """Return the repository SSL certificate directory."""
    return Path(__file__).resolve().parents[4] / "ssl-certs"


def ensure_ssl_files(cert_dir: Path | None = None) -> SSLFiles:
    """Return SSL files, creating a self-signed certificate if needed."""
    resolved_cert_dir = cert_dir or default_ssl_cert_dir()
    resolved_cert_dir.mkdir(parents=True, exist_ok=True)

    ssl_files = SSLFiles(
        cert_file=resolved_cert_dir / CERT_FILE_NAME,
        key_file=resolved_cert_dir / KEY_FILE_NAME,
    )

    if ssl_files.cert_file.exists() and ssl_files.key_file.exists():
        return ssl_files

    _create_self_signed_certificate(ssl_files)
    return ssl_files


def _create_self_signed_certificate(ssl_files: SSLFiles) -> None:
    """Create a self-signed certificate for bgpx.net and local development."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_SIZE_BITS)

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "IR"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "BGPX"),
            x509.NameAttribute(NameOID.COMMON_NAME, CERT_COMMON_NAME),
        ]
    )

    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=VALIDITY_YEARS * 365))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("bgpx.net"),
                    x509.DNSName("localhost"),
                    x509.IPAddress(ip_address("127.0.0.1")),
                    x509.IPAddress(ip_address("::1")),
                ]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(private_key, hashes.SHA256())
    )

    ssl_files.key_file.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    ssl_files.key_file.chmod(0o600)
    ssl_files.cert_file.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))