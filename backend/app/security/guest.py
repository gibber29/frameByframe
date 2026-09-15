import hashlib
import hmac
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class GuestIdentity:
    id: uuid.UUID
    token: str
    is_new: bool


class GuestTokenManager:
    def __init__(self, secret: str) -> None:
        self.secret = secret.encode("utf-8")

    def _signature(self, value: str) -> str:
        return hmac.new(self.secret, value.encode("ascii"), hashlib.sha256).hexdigest()

    def issue(self) -> GuestIdentity:
        guest_id = uuid.uuid4()
        value = str(guest_id)
        return GuestIdentity(guest_id, f"{value}.{self._signature(value)}", True)

    def resolve(self, token: str | None) -> GuestIdentity:
        if token:
            try:
                value, signature = token.rsplit(".", 1)
                guest_id = uuid.UUID(value)
                if hmac.compare_digest(signature, self._signature(value)):
                    return GuestIdentity(guest_id, token, False)
            except (ValueError, AttributeError):
                pass
        return self.issue()
