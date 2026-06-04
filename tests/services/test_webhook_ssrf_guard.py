"""Unit tests for the SSRF guard (webhook_ssrf_guard.py, Issue #47).

All DNS-resolving tests mock socket.getaddrinfo so no real network
calls are made.  Public-IP and IP-literal tests use the ipaddress module
only, which is pure Python and needs no mocking.
"""

from unittest.mock import patch

import pytest

from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.services.webhook_ssrf_guard import _is_public_ip, validate_webhook_url

_MOCK_DNS = "vos_studio_mcp.services.webhook_ssrf_guard.socket.getaddrinfo"

# A minimal getaddrinfo return value for a public IP
_PUBLIC_ADDR = [(2, 1, 6, "", ("93.184.216.34", 0))]   # example.com


# ---------------------------------------------------------------------------
# _is_public_ip helpers
# ---------------------------------------------------------------------------


class TestIsPublicIp:
    def test_public_ipv4(self) -> None:
        assert _is_public_ip("8.8.8.8") is True

    def test_loopback_ipv4(self) -> None:
        assert _is_public_ip("127.0.0.1") is False

    def test_loopback_ipv6(self) -> None:
        assert _is_public_ip("::1") is False

    def test_private_10_block(self) -> None:
        assert _is_public_ip("10.0.0.1") is False

    def test_private_172_block(self) -> None:
        assert _is_public_ip("172.16.0.1") is False
        assert _is_public_ip("172.31.255.255") is False

    def test_private_192_168(self) -> None:
        assert _is_public_ip("192.168.1.1") is False

    def test_link_local(self) -> None:
        assert _is_public_ip("169.254.1.1") is False

    def test_cloud_metadata_endpoint(self) -> None:
        assert _is_public_ip("169.254.169.254") is False

    def test_multicast_ipv4(self) -> None:
        assert _is_public_ip("224.0.0.1") is False

    def test_unspecified(self) -> None:
        assert _is_public_ip("0.0.0.0") is False

    def test_unparseable_string(self) -> None:
        assert _is_public_ip("not-an-ip") is False


# ---------------------------------------------------------------------------
# validate_webhook_url — scheme check
# ---------------------------------------------------------------------------


class TestValidateReturnsIp:
    """validate_webhook_url must return the pinned IP for the caller to use."""

    def test_returns_ip_for_hostname(self) -> None:
        with patch(_MOCK_DNS, return_value=_PUBLIC_ADDR):
            ip = validate_webhook_url("https://example.com/hook")
        assert ip == "93.184.216.34"

    def test_returns_ip_for_ipv4_literal(self) -> None:
        ip = validate_webhook_url("https://93.184.216.34/hook")
        assert ip == "93.184.216.34"

    def test_returns_ip_for_ipv6_literal(self) -> None:
        ip = validate_webhook_url("https://[2607:f8b0:4004:800::200e]/hook")
        assert ip == "2607:f8b0:4004:800::200e"


class TestSchemeValidation:
    def test_https_accepted(self) -> None:
        with patch(_MOCK_DNS, return_value=_PUBLIC_ADDR):
            validate_webhook_url("https://example.com/hook")  # must not raise

    def test_http_rejected(self) -> None:
        with pytest.raises(VosError) as exc_info:
            validate_webhook_url("http://example.com/hook")
        assert exc_info.value.error_code == ErrorCode.INVALID_INPUT
        assert "HTTPS" in str(exc_info.value)

    def test_ftp_rejected(self) -> None:
        with pytest.raises(VosError):
            validate_webhook_url("ftp://example.com/hook")

    def test_no_scheme_rejected(self) -> None:
        with pytest.raises(VosError):
            validate_webhook_url("example.com/hook")

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(VosError):
            validate_webhook_url("")

    def test_no_hostname_rejected(self) -> None:
        with pytest.raises(VosError):
            validate_webhook_url("https:///path")


# ---------------------------------------------------------------------------
# validate_webhook_url — IP literal targets
# ---------------------------------------------------------------------------


class TestIpLiteralTargets:
    def test_public_ip_accepted(self) -> None:
        validate_webhook_url("https://93.184.216.34/hook")  # must not raise

    def test_localhost_ip_rejected(self) -> None:
        with pytest.raises(VosError) as exc_info:
            validate_webhook_url("https://127.0.0.1/hook")
        assert exc_info.value.error_code == ErrorCode.INVALID_INPUT

    def test_loopback_other_rejected(self) -> None:
        with pytest.raises(VosError):
            validate_webhook_url("https://127.255.0.1/hook")

    def test_private_10_rejected(self) -> None:
        with pytest.raises(VosError):
            validate_webhook_url("https://10.0.0.1/hook")

    def test_private_192_168_rejected(self) -> None:
        with pytest.raises(VosError):
            validate_webhook_url("https://192.168.1.1/hook")

    def test_private_172_16_rejected(self) -> None:
        with pytest.raises(VosError):
            validate_webhook_url("https://172.16.0.1/hook")

    def test_link_local_rejected(self) -> None:
        with pytest.raises(VosError):
            validate_webhook_url("https://169.254.0.1/hook")

    def test_cloud_metadata_rejected(self) -> None:
        with pytest.raises(VosError):
            validate_webhook_url("https://169.254.169.254/latest/meta-data/")

    def test_ipv6_loopback_rejected(self) -> None:
        with pytest.raises(VosError):
            validate_webhook_url("https://[::1]/hook")

    def test_ipv6_public_accepted(self) -> None:
        # 2607:f8b0:4004::/48 is a public Google IP block
        validate_webhook_url("https://[2607:f8b0:4004:800::200e]/hook")


# ---------------------------------------------------------------------------
# validate_webhook_url — hostname DNS resolution
# ---------------------------------------------------------------------------


class TestHostnameDnsResolution:
    def test_public_hostname_accepted(self) -> None:
        with patch(_MOCK_DNS, return_value=_PUBLIC_ADDR):
            validate_webhook_url("https://example.com/hook")

    def test_hostname_resolving_to_private_rejected(self) -> None:
        private_addr = [(2, 1, 6, "", ("10.0.0.1", 0))]
        with patch(_MOCK_DNS, return_value=private_addr), pytest.raises(VosError) as exc_info:
            validate_webhook_url("https://internal.example.com/hook")
        assert exc_info.value.error_code == ErrorCode.INVALID_INPUT

    def test_hostname_resolving_to_loopback_rejected(self) -> None:
        loopback_addr = [(2, 1, 6, "", ("127.0.0.1", 0))]
        with patch(_MOCK_DNS, return_value=loopback_addr), pytest.raises(VosError):
            validate_webhook_url("https://localhost/hook")

    def test_hostname_resolving_to_cloud_metadata_rejected(self) -> None:
        metadata_addr = [(2, 1, 6, "", ("169.254.169.254", 0))]
        with patch(_MOCK_DNS, return_value=metadata_addr), pytest.raises(VosError):
            validate_webhook_url("https://metadata.example.com/hook")

    def test_dns_resolution_failure_rejected(self) -> None:
        import socket

        with patch(_MOCK_DNS, side_effect=socket.gaierror("NXDOMAIN")), pytest.raises(VosError) as exc_info:
            validate_webhook_url("https://no-such-host.invalid/hook")
        assert exc_info.value.error_code == ErrorCode.INVALID_INPUT
        assert "could not be resolved" in str(exc_info.value)

    def test_any_private_ip_in_multi_addr_response_rejects(self) -> None:
        """If even one resolved IP is private, the URL must be rejected."""
        mixed_addrs = [
            (2, 1, 6, "", ("93.184.216.34", 0)),  # public
            (2, 1, 6, "", ("10.0.0.1", 0)),        # private — should trigger rejection
        ]
        with patch(_MOCK_DNS, return_value=mixed_addrs), pytest.raises(VosError):
            validate_webhook_url("https://mixed.example.com/hook")


# ---------------------------------------------------------------------------
# validate_webhook_url — edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_url_with_path_and_query_accepted(self) -> None:
        with patch(_MOCK_DNS, return_value=_PUBLIC_ADDR):
            validate_webhook_url(
                "https://api.example.com/webhooks/vos?token=abc&version=2"
            )

    def test_url_with_port_accepted(self) -> None:
        with patch(_MOCK_DNS, return_value=_PUBLIC_ADDR):
            validate_webhook_url("https://example.com:8443/hook")

    def test_localhost_by_name_rejected(self) -> None:
        loopback_addr = [(2, 1, 6, "", ("127.0.0.1", 0))]
        with patch(_MOCK_DNS, return_value=loopback_addr), pytest.raises(VosError):
            validate_webhook_url("https://localhost/hook")


# ---------------------------------------------------------------------------
# check_webhook_url (async wrapper)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_webhook_url_passes_for_public_url() -> None:
    from vos_studio_mcp.services.webhook_ssrf_guard import check_webhook_url

    with patch(_MOCK_DNS, return_value=_PUBLIC_ADDR):
        ip = await check_webhook_url("https://example.com/hook")
    assert ip == "93.184.216.34"


@pytest.mark.asyncio
async def test_check_webhook_url_raises_for_private_ip() -> None:
    from vos_studio_mcp.services.webhook_ssrf_guard import check_webhook_url

    with pytest.raises(VosError):
        await check_webhook_url("https://192.168.0.1/hook")
