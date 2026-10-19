from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import re
import secrets
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from state_store import AtomicJsonStore


SESSION_COOKIE = "metube_session"
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
INVITATION_TTL_SECONDS = 7 * 24 * 60 * 60
PASSWORD_MIN_LENGTH = 12
USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
ROLES = frozenset(("admin", "user"))
_SCRYPT_N = 1 << 15
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_MAXMEM = 64 * 1024 * 1024


class AuthError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class AuthIdentity:
    user_id: str
    username: str
    role: str
    credential_type: str
    credential_hash: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _now() -> int:
    return int(time.time())


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _username_key(username: str) -> str:
    return username.casefold()


def _validate_username(username: Any) -> str:
    if not isinstance(username, str):
        raise AuthError(400, "Username must be a string")
    value = username.strip()
    if not USERNAME_RE.fullmatch(value):
        raise AuthError(
            400,
            "Username must be 3-64 characters and contain only letters, numbers, '.', '_' or '-'",
        )
    return value


def _validate_password(password: Any) -> str:
    if not isinstance(password, str) or len(password) < PASSWORD_MIN_LENGTH:
        raise AuthError(400, f"Password must contain at least {PASSWORD_MIN_LENGTH} characters")
    if len(password) > 1024:
        raise AuthError(400, "Password is too long")
    return password


def _validate_role(role: Any) -> str:
    if role not in ROLES:
        raise AuthError(400, "Role must be 'admin' or 'user'")
    return str(role)


def _derive_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        maxmem=_SCRYPT_MAXMEM,
        dklen=32,
    )


async def _password_record(password: str) -> tuple[str, str]:
    password = _validate_password(password)
    salt = secrets.token_bytes(16)
    derived = await asyncio.to_thread(_derive_password, password, salt)
    return (
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(derived).decode("ascii"),
    )


async def _password_matches(password: str, salt_text: str, hash_text: str) -> bool:
    try:
        salt = base64.b64decode(salt_text.encode("ascii"), validate=True)
        expected = base64.b64decode(hash_text.encode("ascii"), validate=True)
        actual = await asyncio.to_thread(_derive_password, password, salt)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


class AuthManager:
    def __init__(self, state_dir: str):
        self.store = AtomicJsonStore(
            f"{state_dir}/auth.json",
            kind="auth",
        )
        self._lock = asyncio.Lock()
        self._login_failures: dict[str, deque[int]] = defaultdict(deque)
        payload = self.store.load() or {}
        self.users: dict[str, dict[str, Any]] = self._dict(payload.get("users"))
        self.sessions: dict[str, dict[str, Any]] = self._dict(payload.get("sessions"))
        self.invitations: dict[str, dict[str, Any]] = self._dict(payload.get("invitations"))
        self.api_tokens: dict[str, dict[str, Any]] = self._dict(payload.get("api_tokens"))
        self._cleanup_expired()

    @staticmethod
    def _dict(value: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(value, dict):
            return {}
        return {str(k): v for k, v in value.items() if isinstance(v, dict)}

    @property
    def setup_required(self) -> bool:
        return not self.users

    def _save(self) -> None:
        self.store.save(
            {
                "users": self.users,
                "sessions": self.sessions,
                "invitations": self.invitations,
                "api_tokens": self.api_tokens,
            }
        )

    def _cleanup_expired(self) -> bool:
        now = _now()
        old_sessions = [
            key
            for key, value in self.sessions.items()
            if value.get("expires_at", 0) <= now
        ]
        old_invitations = [
            key for key, value in self.invitations.items() if value.get("expires_at", 0) <= now
        ]
        for key in old_sessions:
            self.sessions.pop(key, None)
        for key in old_invitations:
            self.invitations.pop(key, None)
        return bool(old_sessions or old_invitations)

    def _find_user_by_name(self, username: str) -> dict[str, Any] | None:
        key = _username_key(username)
        return next((user for user in self.users.values() if user.get("username_key") == key), None)

    def _public_user(self, user: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "active": bool(user.get("active", True)),
            "created_at": user["created_at"],
            "updated_at": user["updated_at"],
        }

    def _identity(
        self,
        user: dict[str, Any],
        credential_type: str,
        credential_hash: str,
    ) -> AuthIdentity:
        return AuthIdentity(
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            credential_type=credential_type,
            credential_hash=credential_hash,
        )

    def _active_admin_count(self, *, excluding: str | None = None) -> int:
        return sum(
            1
            for user in self.users.values()
            if user["id"] != excluding
            and user.get("active", True)
            and user.get("role") == "admin"
        )

    async def create_first_user(self, username: Any, password: Any) -> tuple[dict[str, Any], str]:
        username = _validate_username(username)
        salt, password_hash = await _password_record(password)
        async with self._lock:
            if self.users:
                raise AuthError(409, "Onboarding has already been completed")
            user = self._new_user(username, "admin", salt, password_hash)
            self.users[user["id"]] = user
            raw_session = self._new_session(user["id"])
            self._save()
            return self._public_user(user), raw_session

    def _new_user(
        self,
        username: str,
        role: str,
        salt: str,
        password_hash: str,
    ) -> dict[str, Any]:
        now = _now()
        user_id = uuid.uuid4().hex
        return {
            "id": user_id,
            "username": username,
            "username_key": _username_key(username),
            "role": role,
            "active": True,
            "password_salt": salt,
            "password_hash": password_hash,
            "created_at": now,
            "updated_at": now,
        }

    def _new_session(self, user_id: str) -> str:
        raw = secrets.token_urlsafe(32)
        now = _now()
        self.sessions[_digest(raw)] = {
            "user_id": user_id,
            "created_at": now,
            "expires_at": now + SESSION_TTL_SECONDS,
        }
        return raw

    async def login(
        self,
        username: Any,
        password: Any,
        remote: str,
    ) -> tuple[dict[str, Any], str]:
        supplied_username = username.strip() if isinstance(username, str) else ""
        supplied_password = password if isinstance(password, str) else ""
        failure_key = f"{remote}|{_username_key(supplied_username)}"
        self._check_rate_limit(failure_key)

        async with self._lock:
            user = self._find_user_by_name(supplied_username)
            password_salt = user.get("password_salt", "") if user else ""
            password_hash = user.get("password_hash", "") if user else ""
        if not user or not await _password_matches(supplied_password, password_salt, password_hash):
            self._record_login_failure(failure_key)
            raise AuthError(401, "Invalid username or password")
        if not user.get("active", True):
            self._record_login_failure(failure_key)
            raise AuthError(401, "Invalid username or password")

        async with self._lock:
            current = self.users.get(user["id"])
            if not current or not current.get("active", True):
                raise AuthError(401, "Invalid username or password")
            raw_session = self._new_session(current["id"])
            self._save()
            self._login_failures.pop(failure_key, None)
            return self._public_user(current), raw_session

    def _check_rate_limit(self, key: str) -> None:
        failures = self._login_failures[key]
        cutoff = _now() - 15 * 60
        while failures and failures[0] <= cutoff:
            failures.popleft()
        if len(failures) >= 5:
            raise AuthError(429, "Too many login attempts; try again later")

    def _record_login_failure(self, key: str) -> None:
        self._login_failures[key].append(_now())

    async def authenticate(
        self,
        session_cookie: str | None,
        authorization: str | None,
    ) -> AuthIdentity | None:
        credential_type = ""
        raw = ""
        if authorization:
            scheme, _, value = authorization.partition(" ")
            if scheme.lower() == "bearer" and value:
                credential_type = "token"
                raw = value.strip()
        if not raw and session_cookie:
            credential_type = "session"
            raw = session_cookie
        if not raw:
            return None

        credential_hash = _digest(raw)
        async with self._lock:
            changed = self._cleanup_expired()
            records = self.api_tokens if credential_type == "token" else self.sessions
            record = records.get(credential_hash)
            user = self.users.get(record.get("user_id")) if record else None
            if not user or not user.get("active", True):
                if record:
                    records.pop(credential_hash, None)
                    changed = True
                if changed:
                    self._save()
                return None
            if credential_type == "token":
                last_used = int(record.get("last_used_at") or 0)
                if _now() - last_used >= 300:
                    record["last_used_at"] = _now()
                    changed = True
            if changed:
                self._save()
            return self._identity(user, credential_type, credential_hash)

    async def logout(self, raw_session: str | None) -> str | None:
        if not raw_session:
            return None
        session_hash = _digest(raw_session)
        async with self._lock:
            session = self.sessions.pop(session_hash, None)
            if session:
                self._save()
                return session_hash
        return None

    async def list_users(self) -> list[dict[str, Any]]:
        async with self._lock:
            return sorted(
                (self._public_user(user) for user in self.users.values()),
                key=lambda item: item["username"].casefold(),
            )

    async def update_user(
        self,
        actor: AuthIdentity,
        user_id: str,
        changes: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        allowed = {"username", "role", "active"}
        if not changes or any(key not in allowed for key in changes):
            raise AuthError(400, "No valid user fields to update")
        async with self._lock:
            user = self.users.get(user_id)
            if not user:
                raise AuthError(404, "User not found")
            username = _validate_username(changes.get("username", user["username"]))
            role = _validate_role(changes.get("role", user["role"]))
            active = changes.get("active", user.get("active", True))
            if not isinstance(active, bool):
                raise AuthError(400, "Active must be a boolean")
            duplicate = self._find_user_by_name(username)
            if duplicate and duplicate["id"] != user_id:
                raise AuthError(409, "Username already exists")
            removes_admin = user["role"] == "admin" and user.get("active", True) and (
                role != "admin" or not active
            )
            if removes_admin and self._active_admin_count(excluding=user_id) == 0:
                raise AuthError(409, "The last active administrator cannot be changed")
            if actor.user_id == user_id and not active:
                raise AuthError(409, "You cannot disable your own account")
            user.update(
                {
                    "username": username,
                    "username_key": _username_key(username),
                    "role": role,
                    "active": active,
                    "updated_at": _now(),
                }
            )
            revoke = not active
            if revoke:
                self._revoke_user_access_locked(user_id)
            self._save()
            return self._public_user(user), revoke

    async def delete_user(self, actor: AuthIdentity, user_id: str) -> bool:
        async with self._lock:
            user = self.users.get(user_id)
            if not user:
                raise AuthError(404, "User not found")
            if actor.user_id == user_id:
                raise AuthError(409, "You cannot delete your own account")
            if (
                user["role"] == "admin"
                and user.get("active", True)
                and self._active_admin_count(excluding=user_id) == 0
            ):
                raise AuthError(409, "The last active administrator cannot be deleted")
            self.users.pop(user_id)
            self._revoke_user_access_locked(user_id)
            self._save()
            return True

    def _revoke_user_access_locked(self, user_id: str, keep_session: str | None = None) -> None:
        for key in [
            key
            for key, value in self.sessions.items()
            if value.get("user_id") == user_id and key != keep_session
        ]:
            self.sessions.pop(key, None)
        for key in [
            key for key, value in self.api_tokens.items() if value.get("user_id") == user_id
        ]:
            self.api_tokens.pop(key, None)

    async def revoke_user_access(self, user_id: str) -> None:
        async with self._lock:
            if user_id not in self.users:
                raise AuthError(404, "User not found")
            self._revoke_user_access_locked(user_id)
            self._save()

    async def change_password(
        self,
        identity: AuthIdentity,
        current_password: Any,
        new_password: Any,
    ) -> None:
        new_password = _validate_password(new_password)
        async with self._lock:
            user = self.users.get(identity.user_id)
            if not user:
                raise AuthError(404, "User not found")
            salt_text = user["password_salt"]
            hash_text = user["password_hash"]
        if not isinstance(current_password, str) or not await _password_matches(
            current_password, salt_text, hash_text
        ):
            raise AuthError(401, "Current password is incorrect")
        salt, password_hash = await _password_record(new_password)
        async with self._lock:
            user = self.users.get(identity.user_id)
            if not user:
                raise AuthError(404, "User not found")
            user["password_salt"] = salt
            user["password_hash"] = password_hash
            user["updated_at"] = _now()
            keep = identity.credential_hash if identity.credential_type == "session" else None
            self._revoke_user_access_locked(identity.user_id, keep_session=keep)
            self._save()

    async def create_invitation(self, actor: AuthIdentity, role: Any) -> dict[str, Any]:
        role = _validate_role(role)
        raw = secrets.token_urlsafe(32)
        invitation_hash = _digest(raw)
        now = _now()
        invitation = {
            "id": uuid.uuid4().hex,
            "role": role,
            "created_by": actor.user_id,
            "created_at": now,
            "expires_at": now + INVITATION_TTL_SECONDS,
        }
        async with self._lock:
            self._cleanup_expired()
            self.invitations[invitation_hash] = invitation
            self._save()
        return {**invitation, "token": raw}

    async def list_invitations(self) -> list[dict[str, Any]]:
        async with self._lock:
            if self._cleanup_expired():
                self._save()
            return sorted(
                (dict(value) for value in self.invitations.values()),
                key=lambda item: item["created_at"],
                reverse=True,
            )

    async def inspect_invitation(self, raw: str) -> dict[str, Any]:
        async with self._lock:
            if self._cleanup_expired():
                self._save()
            invitation = self.invitations.get(_digest(raw))
            if not invitation:
                raise AuthError(404, "Invitation is invalid or has expired")
            return {
                "id": invitation["id"],
                "role": invitation["role"],
                "expires_at": invitation["expires_at"],
            }

    async def revoke_invitation(self, invitation_id: str) -> None:
        async with self._lock:
            key = next(
                (
                    key
                    for key, invitation in self.invitations.items()
                    if invitation.get("id") == invitation_id
                ),
                None,
            )
            if not key:
                raise AuthError(404, "Invitation not found")
            self.invitations.pop(key)
            self._save()

    async def accept_invitation(
        self,
        raw: str,
        username: Any,
        password: Any,
    ) -> tuple[dict[str, Any], str]:
        username = _validate_username(username)
        salt, password_hash = await _password_record(password)
        invitation_hash = _digest(raw)
        async with self._lock:
            self._cleanup_expired()
            invitation = self.invitations.get(invitation_hash)
            if not invitation:
                raise AuthError(404, "Invitation is invalid or has expired")
            if self._find_user_by_name(username):
                raise AuthError(409, "Username already exists")
            user = self._new_user(username, invitation["role"], salt, password_hash)
            self.users[user["id"]] = user
            self.invitations.pop(invitation_hash)
            raw_session = self._new_session(user["id"])
            self._save()
            return self._public_user(user), raw_session

    async def create_api_token(self, identity: AuthIdentity, name: Any) -> dict[str, Any]:
        if not isinstance(name, str) or not name.strip():
            raise AuthError(400, "Token name is required")
        clean_name = name.strip()
        if len(clean_name) > 100:
            raise AuthError(400, "Token name is too long")
        raw = "mtu_" + secrets.token_urlsafe(32)
        token_hash = _digest(raw)
        now = _now()
        record = {
            "id": uuid.uuid4().hex,
            "user_id": identity.user_id,
            "name": clean_name,
            "prefix": raw[:12],
            "created_at": now,
            "last_used_at": None,
        }
        async with self._lock:
            self.api_tokens[token_hash] = record
            self._save()
        return {**self._public_token(record), "token": raw}

    def _public_token(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": record["id"],
            "name": record["name"],
            "prefix": record["prefix"],
            "created_at": record["created_at"],
            "last_used_at": record.get("last_used_at"),
        }

    async def list_api_tokens(self, user_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            return sorted(
                (
                    self._public_token(record)
                    for record in self.api_tokens.values()
                    if record.get("user_id") == user_id
                ),
                key=lambda item: item["created_at"],
                reverse=True,
            )

    async def revoke_api_token(self, user_id: str, token_id: str) -> None:
        async with self._lock:
            key = next(
                (
                    key
                    for key, record in self.api_tokens.items()
                    if record.get("id") == token_id and record.get("user_id") == user_id
                ),
                None,
            )
            if not key:
                raise AuthError(404, "API token not found")
            self.api_tokens.pop(key)
            self._save()
