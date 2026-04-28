"""Infra adapter for executing ping using icmplib."""

from __future__ import annotations

import re
import subprocess

from icmplib import ICMPRequest, ICMPv4Socket, ICMPv6Socket, is_hostname, is_ipv6_address, resolve
from icmplib.exceptions import ICMPLibError, TimeExceeded
from icmplib.utils import unique_identifier

from models.ping import PingResultModel

from .ping_parser import parse_ping_result


class PingAdapter:
    """Execute ping and return normalized ping result."""

    def run_ping(self, host: str) -> PingResultModel:
        """Run a single ICMP ping probe against host via icmplib."""

        is_alive, ping_time_ms, ttl, ttl_expired = self._probe_once(host)

        return parse_ping_result(
            is_alive=is_alive,
            ping_time_ms=ping_time_ms,
            ttl=ttl,
            ttl_expired=ttl_expired,
        )

    def _probe_once(self, host: str) -> tuple[bool, float | None, int | None, bool]:
        """Execute one ICMP probe and preserve ttl-expired signal when returned."""
        address = host

        if is_hostname(host):
            address = resolve(host, None)[0]

        socket_cls = ICMPv6Socket if is_ipv6_address(address) else ICMPv4Socket
        request = ICMPRequest(destination=address, id=unique_identifier(), sequence=0)

        try:
            with socket_cls(None, False) as sock:
                sock.send(request)
                reply = sock.receive(request, timeout=1)

                if self._is_time_exceeded_reply(reply):
                    return False, None, None, True

                reply.raise_for_status()

            rtt_ms = (reply.time - request.time) * 1000
            ttl = getattr(reply, "ttl", None)
            if ttl is None:
                ttl = self._get_ttl_from_system_ping(str(address))
            return True, rtt_ms, ttl, False
        except TimeExceeded:
            return False, None, None, True
        except ICMPLibError as exc:
            reply = getattr(exc, "reply", None)
            if self._is_time_exceeded_reply(reply):
                return False, None, None, True

            return False, None, None, False

        # Defensive fallback for non-icmplib unexpected failures.
        except Exception:
            return False, None, None, False

    @staticmethod
    def _get_ttl_from_system_ping(address: str) -> int | None:
        """Best-effort fallback to parse TTL from system ping output."""
        try:
            completed = subprocess.run(
                ["ping", "-c", "1", address],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except Exception:
            return None

        output = f"{completed.stdout}\n{completed.stderr}"
        match = re.search(r"ttl[=\s](\d+)", output, flags=re.IGNORECASE)
        if match is None:
            return None

        return int(match.group(1))

    @staticmethod
    def _is_time_exceeded_reply(reply: object | None) -> bool:
        """Return True when an ICMP reply is a TTL-expired/time-exceeded response."""
        if reply is None:
            return False

        family = getattr(reply, "family", getattr(reply, "_family", None))
        reply_type = getattr(reply, "type", getattr(reply, "_type", None))

        return (family == 4 and reply_type == 11) or (family == 6 and reply_type == 3)
