"""Infra adapter for executing traceroute using icmplib."""

from __future__ import annotations

from time import sleep
from typing import Any, cast

from icmplib import Hop, ICMPRequest, is_hostname, is_ipv6_address, resolve
from icmplib.exceptions import ICMPLibError, TimeExceeded
from icmplib.sockets import ICMPv4Socket, ICMPv6Socket
from icmplib.utils import unique_identifier

from models.traceroute import TracerouteResultModel

from .traceroute_parser import parse_traceroute_result


class TracerouteAdapter:
    """Execute traceroute and return normalized traceroute result."""

    _TIMEOUT_SECONDS = 1
    _COUNT_PER_HOP = 1
    _MAX_HOPS = 30

    def run_traceroute(
        self,
        host: str,
    ) -> TracerouteResultModel:
        """Run traceroute probes against host via icmplib."""
        try:
            hops, reached_target = self._execute_traceroute(
                host,
                count=self._COUNT_PER_HOP,
                timeout=self._TIMEOUT_SECONDS,
                max_hops=self._MAX_HOPS,
                fast=True,
            )
            error_message = None
            if hops and not reached_target and self._is_routing_loop(hops):
                error_message = "traceroute completed: routing loop detected"

            return parse_traceroute_result(
                hops=cast(list[object], hops),
                had_error=False,
                reached_target=reached_target,
                error_message=error_message,
            )
        except ICMPLibError as exc:
            return parse_traceroute_result(
                hops=[],
                had_error=True,
                error_message=self._classify_error_message(exc),
            )
        except Exception as exc:
            # Defensive fallback for non-icmplib unexpected failures.
            return parse_traceroute_result(
                hops=[],
                had_error=True,
                error_message=self._classify_error_message(exc),
            )

    @staticmethod
    def _classify_error_message(exc: Exception) -> str:
        """Return a stable, user-facing traceroute failure message."""
        detail = str(exc).strip()
        lowered = detail.lower()

        if any(token in lowered for token in {"permission", "operation not permitted", "not permitted"}):
            return "traceroute failed: insufficient permissions"

        if any(
            token in lowered
            for token in {
                "name or service not known",
                "nxdomain",
                "name lookup",
                "hostname",
                "dns",
                "cannot be resolved",
                "can not be resolved",
                "not be resolved",
                "resolved",
            }
        ):
            return "traceroute failed: name resolution error"

        if any(token in lowered for token in {"timed out", "timeout"}):
            return "traceroute failed: timeout"

        if any(token in lowered for token in {"network is unreachable", "unreachable", "no route to host"}):
            return "traceroute failed: network unreachable"

        if detail:
            return f"traceroute failed: {detail}"

        return "traceroute failed"

    @staticmethod
    def _execute_traceroute(
        host: str,
        *,
        count: int,
        timeout: float,
        max_hops: int,
        fast: bool,
    ) -> tuple[list[Hop], bool]:
        """Execute traceroute with unprivileged ICMP datagram sockets when available."""
        if is_hostname(host):
            host = str(resolve(host)[0])

        socket_cls = ICMPv6Socket if is_ipv6_address(host) else ICMPv4Socket

        traceroute_id = unique_identifier()
        ttl = 1
        host_reached = False
        hops: list[Hop] = []

        with socket_cls(privileged=False) as sock:
            while not host_reached and ttl <= max_hops:
                reply, packets_sent, rtts, reached_on_ttl = TracerouteAdapter._probe_ttl(
                    sock=sock,
                    host=host,
                    traceroute_id=traceroute_id,
                    ttl=ttl,
                    count=count,
                    timeout=timeout,
                    fast=fast,
                )

                host_reached = host_reached or reached_on_ttl
                hops.append(
                    TracerouteAdapter._build_hop(
                        ttl=ttl,
                        count=count,
                        reply=reply,
                        packets_sent=packets_sent,
                        rtts=rtts,
                    )
                )

                ttl += 1

        return hops, host_reached

    @staticmethod
    def _probe_ttl(
        *,
        sock: ICMPv4Socket | ICMPv6Socket,
        host: str,
        traceroute_id: int,
        ttl: int,
        count: int,
        timeout: float,
        fast: bool,
    ) -> tuple[object | None, int, list[float], bool]:
        """Probe a single TTL and return reply metadata for hop construction."""
        reply = None
        packets_sent = 0
        rtts: list[float] = []
        reached_target = False

        for sequence in range(count):
            request = ICMPRequest(destination=host, id=traceroute_id, sequence=sequence, ttl=ttl)

            try:
                sock.send(request)
                packets_sent += 1

                reply = sock.receive(request, int(timeout))
                if reply is None:
                    continue

                rtts.append((reply.time - request.time) * 1000)
                reply.raise_for_status()
                reached_target = True

            except TimeExceeded:
                sleep(0.05)

            except ICMPLibError:
                break

            if fast and reply:
                break

        return reply, packets_sent, rtts, reached_target

    @staticmethod
    def _build_hop(
        *,
        ttl: int,
        count: int,
        reply: object | None,
        packets_sent: int,
        rtts: list[float],
    ) -> Hop:
        """Build normalized hop object for one TTL probe."""
        if not reply:
            return Hop(
                address="*",
                packets_sent=packets_sent or count,
                rtts=rtts,
                distance=ttl,
            )

        source = cast(Any, reply).source
        return Hop(
            address=source,
            packets_sent=packets_sent,
            rtts=rtts,
            distance=ttl,
        )

    @staticmethod
    def _is_routing_loop(hops: list[Hop]) -> bool:
        """Best-effort loop detection for repeated cyclic hop addresses."""
        addresses = [str(hop.address) for hop in hops if str(hop.address) != "*"]
        if len(addresses) < 6:
            return False

        tail = addresses[-6:]
        unique_tail = set(tail)
        if len(unique_tail) <= 2:
            return True

        if len(unique_tail) == 3 and tail[0:3] == tail[3:6]:
            return True

        return False
