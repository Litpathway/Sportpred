from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import Settings


@dataclass(frozen=True)
class CodeValidation:
    valid: bool
    genuine: bool
    selection_ids: tuple[int, ...] = ()


class BookingProvider(Protocol):
    name: str
    genuine_capable: bool

    def create_code(self, selections: list[dict], idempotency_key: str) -> str | None: ...
    def validate_code(self, code: str) -> CodeValidation: ...
    def get_code_status(self, code: str) -> str: ...


class UnavailableBookingProvider:
    name = "unavailable"
    genuine_capable = False

    def create_code(self, selections: list[dict], idempotency_key: str) -> None:
        return None

    def validate_code(self, code: str) -> CodeValidation:
        return CodeValidation(False, False)

    def get_code_status(self, code: str) -> str:
        return "unavailable"


class MockBookingProvider(UnavailableBookingProvider):
    name = "mock"

    def create_code(self, selections: list[dict], idempotency_key: str) -> str:
        return f"MOCK-{idempotency_key[:12].upper()}"

    def validate_code(self, code: str) -> CodeValidation:
        return CodeValidation(code.startswith("MOCK-"), False)

    def get_code_status(self, code: str) -> str:
        return "simulated"


class AuthorizedBookingProvider:
    """Normalized gateway contract; configure only a provider you are authorized to use.

    Paths below are this application's documented gateway contract, not claims
    about any bookmaker's endpoints. Implement the gateway for your provider.
    """
    name = "authorized"
    genuine_capable = True

    def __init__(self, settings: Settings):
        if not settings.booking_api_url or not settings.booking_api_token or not settings.booking_api_url.startswith("https://"):
            raise ValueError("Authorized booking gateway requires HTTPS URL and token")
        self.base = settings.booking_api_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {settings.booking_api_token}"}

    def create_code(self, selections: list[dict], idempotency_key: str) -> str:
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            response = client.post(f"{self.base}/codes", json={"selections": selections},
                                   headers={**self.headers, "Idempotency-Key": idempotency_key})
        response.raise_for_status()
        code = response.json().get("code")
        if not isinstance(code, str) or not 1 <= len(code) <= 150:
            raise ValueError("Gateway returned invalid code")
        return code

    def validate_code(self, code: str) -> CodeValidation:
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            response = client.post(f"{self.base}/validate", json={"code": code}, headers=self.headers)
        response.raise_for_status()
        result = response.json()
        ids = result.get("selection_ids", [])
        if not isinstance(ids, list) or not all(type(i) is int for i in ids):
            raise ValueError("Invalid gateway validation response")
        return CodeValidation(result.get("valid") is True, result.get("genuine") is True, tuple(ids))

    def get_code_status(self, code: str) -> str:
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            response = client.post(f"{self.base}/status", json={"code": code}, headers=self.headers)
        response.raise_for_status()
        status = response.json().get("status")
        return status if status in {"active", "expired", "cancelled"} else "unknown"


def booking_provider(settings: Settings) -> BookingProvider:
    if settings.booking_provider == "authorized":
        return AuthorizedBookingProvider(settings)
    if settings.booking_provider == "mock" and settings.demo_mode:
        return MockBookingProvider()
    return UnavailableBookingProvider()
