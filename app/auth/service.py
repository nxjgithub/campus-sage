from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from app.auth.dto import CurrentUser, TokenPair
from app.auth.passwords import PasswordHasher
from app.auth.permissions import DEFAULT_ROLE_PERMISSIONS, resolve_permissions
from app.auth.tokens import TokenService
from app.core.error_codes import ErrorCode
from app.core.errors import AppError
from app.core.settings import Settings
from app.core.utils import new_id, utc_now_iso
from app.db.models import (
    KbAccessRecord,
    RefreshTokenRecord,
    RoleRecord,
    UserRecord,
)
from app.db.repos.interfaces import (
    KbAccessRepositoryProtocol,
    RefreshTokenRepositoryProtocol,
    RoleRepositoryProtocol,
    UserRepositoryProtocol,
)


class UserService:
    """用户管理服务。"""

    def __init__(
        self,
        user_repo: UserRepositoryProtocol,
        role_repo: RoleRepositoryProtocol,
        kb_access_repo: KbAccessRepositoryProtocol,
        settings: Settings,
    ) -> None:
        self._user_repo = user_repo
        self._role_repo = role_repo
        self._kb_access_repo = kb_access_repo
        self._hasher = PasswordHasher(settings)

    def create_user(self, email: str, password: str, roles: list[str]) -> UserRecord:
        """创建用户并分配角色。"""

        if self._user_repo.get_by_email(email):
            raise AppError(
                code=ErrorCode.USER_ALREADY_EXISTS,
                message="用户邮箱已存在",
                detail={"email": email},
                status_code=409,
            )
        now = utc_now_iso()
        record = UserRecord(
            user_id=new_id("user"),
            email=email,
            password_hash=self._hasher.hash_password(password),
            status="active",
            created_at=now,
            updated_at=now,
            last_login_at=None,
        )
        self._user_repo.create(record)
        self._validate_roles(roles)
        self._user_repo.set_roles(record.user_id, roles)
        return record

    def list_users(
        self,
        status: str | None,
        keyword: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[UserRecord], int]:
        """按条件分页列出用户。"""

        items = self._user_repo.list_filtered(status, keyword, limit, offset)
        total = self._user_repo.count_filtered(status, keyword)
        return items, total

    def get_user(self, user_id: str) -> UserRecord:
        """获取用户。"""

        record = self._user_repo.get(user_id)
        if record is None or record.status == "deleted":
            raise AppError(
                code=ErrorCode.USER_NOT_FOUND,
                message="用户不存在",
                detail={"user_id": user_id},
                status_code=404,
            )
        return record

    def update_user(
        self,
        user_id: str,
        status: str | None,
        roles: list[str] | None,
        password: str | None,
    ) -> UserRecord:
        """更新用户信息。"""

        record = self.get_user(user_id)
        if status is not None:
            record.status = status
        if password is not None:
            record.password_hash = self._hasher.hash_password(password)
        record.updated_at = utc_now_iso()
        self._user_repo.update(record)
        if roles is not None:
            self._validate_roles(roles)
            self._user_repo.set_roles(record.user_id, roles)
        return record

    def list_roles(self, user_id: str) -> list[RoleRecord]:
        """列出用户角色。"""

        return self._user_repo.list_roles(user_id)

    def list_all_roles(self) -> list[RoleRecord]:
        """列出所有角色。"""

        return self._role_repo.list_all()

    def upsert_kb_access(
        self, user_id: str, kb_id: str, access_level: str
    ) -> KbAccessRecord:
        """写入知识库访问权限。"""

        record = KbAccessRecord(
            user_id=user_id,
            kb_id=kb_id,
            access_level=access_level,
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        return self._kb_access_repo.upsert(record)

    def remove_kb_access(self, user_id: str, kb_id: str) -> bool:
        """删除用户知识库权限。"""

        return self._kb_access_repo.delete(user_id, kb_id)

    def list_kb_access(self, user_id: str) -> list[KbAccessRecord]:
        """列出用户知识库权限。"""

        return self._kb_access_repo.list_by_user(user_id)

    def replace_kb_access(
        self, user_id: str, items: list[dict[str, str]]
    ) -> list[KbAccessRecord]:
        """批量替换用户知识库权限。"""

        now = utc_now_iso()
        records = [
            KbAccessRecord(
                user_id=user_id,
                kb_id=item["kb_id"],
                access_level=item["access_level"],
                created_at=now,
                updated_at=now,
            )
            for item in items
        ]
        self._kb_access_repo.replace_by_user(user_id, records)
        return records

    def ensure_roles_seeded(self) -> None:
        """确保默认角色存在。"""

        for name, permissions in DEFAULT_ROLE_PERMISSIONS.items():
            if self._role_repo.get_by_name(name):
                continue
            record = RoleRecord(
                role_id=f"role_{name}",
                name=name,
                permissions_json=_dump_permissions(permissions),
                created_at=utc_now_iso(),
            )
            self._role_repo.create(record)

    def _validate_roles(self, roles: list[str]) -> None:
        """校验角色是否存在。"""

        for role_name in roles:
            if self._role_repo.get_by_name(role_name) is None:
                raise AppError(
                    code=ErrorCode.ROLE_NOT_FOUND,
                    message="角色不存在",
                    detail={"role": role_name},
                    status_code=400,
                )


class AuthService:
    """认证服务。"""

    def __init__(
        self,
        user_repo: UserRepositoryProtocol,
        role_repo: RoleRepositoryProtocol,
        refresh_repo: RefreshTokenRepositoryProtocol,
        settings: Settings,
    ) -> None:
        self._user_repo = user_repo
        self._role_repo = role_repo
        self._refresh_repo = refresh_repo
        self._hasher = PasswordHasher(settings)
        self._token_service = TokenService(settings)
        self._refresh_days = settings.refresh_token_expire_days

    def login(self, email: str, password: str) -> tuple[TokenPair, UserRecord, list[str]]:
        """用户登录并签发令牌。"""

        user = self._user_repo.get_by_email(email)
        if user is None or user.status == "deleted":
            raise AppError(
                code=ErrorCode.AUTH_INVALID_CREDENTIALS,
                message="账号或密码错误",
                detail=None,
                status_code=401,
            )
        if user.status != "active":
            raise AppError(
                code=ErrorCode.USER_DISABLED,
                message="账号已被禁用",
                detail={"user_id": user.user_id},
                status_code=403,
            )
        if not self._hasher.verify_password(password, user.password_hash):
            raise AppError(
                code=ErrorCode.AUTH_INVALID_CREDENTIALS,
                message="账号或密码错误",
                detail=None,
                status_code=401,
            )
        token_pair = self._issue_tokens(user.user_id)
        user.last_login_at = utc_now_iso()
        user.updated_at = utc_now_iso()
        self._user_repo.update(user)
        roles = [role.name for role in self._user_repo.list_roles(user.user_id)]
        return token_pair, user, roles

    def refresh(self, refresh_token: str) -> TokenPair:
        """刷新访问令牌并轮换刷新令牌。"""

        record = self._refresh_repo.get_by_hash(_hash_token(refresh_token))
        if record is None or record.revoked:
            raise AppError(
                code=ErrorCode.AUTH_TOKEN_INVALID,
                message="刷新令牌无效",
                detail=None,
                status_code=401,
            )
        if _is_expired(record.expires_at):
            raise AppError(
                code=ErrorCode.AUTH_TOKEN_EXPIRED,
                message="刷新令牌已过期",
                detail=None,
                status_code=401,
            )
        user = self._user_repo.get(record.user_id)
        if user is None or user.status != "active":
            raise AppError(
                code=ErrorCode.USER_DISABLED,
                message="账号已被禁用",
                detail={"user_id": record.user_id},
                status_code=403,
            )
        self._refresh_repo.revoke(record.token_id, utc_now_iso())
        return self._issue_tokens(record.user_id)

    def logout(self, refresh_token: str) -> None:
        """注销刷新令牌。"""

        record = self._refresh_repo.get_by_hash(_hash_token(refresh_token))
        if record is None:
            return
        if record.revoked:
            return
        self._refresh_repo.revoke(record.token_id, utc_now_iso())

    def build_current_user(self, user_id: str) -> CurrentUser:
        """构造当前用户上下文。"""

        user = self._user_repo.get(user_id)
        if user is None or user.status == "deleted":
            raise AppError(
                code=ErrorCode.AUTH_UNAUTHORIZED,
                message="用户不存在",
                detail=None,
                status_code=401,
            )
        if user.status != "active":
            raise AppError(
                code=ErrorCode.USER_DISABLED,
                message="账号已被禁用",
                detail={"user_id": user.user_id},
                status_code=403,
            )
        roles = self._user_repo.list_roles(user.user_id)
        permissions = resolve_permissions(roles)
        return CurrentUser(user=user, roles=[role.name for role in roles], permissions=permissions)

    def _issue_tokens(self, user_id: str) -> TokenPair:
        access_token, expires_in = self._token_service.create_access_token(user_id)
        refresh_token = self._token_service.generate_refresh_token()
        expires_at = _future_iso(days=self._refresh_days)
        record = RefreshTokenRecord(
            token_id=new_id("rt"),
            user_id=user_id,
            token_hash=_hash_token(refresh_token),
            expires_at=expires_at,
            revoked=False,
            created_at=utc_now_iso(),
            revoked_at=None,
        )
        self._refresh_repo.create(record)
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
        )


class AuthorizationService:
    """授权与资源访问控制。"""

    def __init__(
        self,
        kb_access_repo: KbAccessRepositoryProtocol,
    ) -> None:
        self._kb_access_repo = kb_access_repo

    def ensure_permission(self, current_user: CurrentUser, permission: str) -> None:
        """校验权限是否满足。"""

        if "*" in current_user.permissions:
            return
        if permission not in current_user.permissions:
            raise AppError(
                code=ErrorCode.AUTH_FORBIDDEN,
                message="权限不足",
                detail={"permission": permission},
                status_code=403,
            )

    def ensure_kb_access(
        self,
        current_user: CurrentUser | None,
        kb_id: str,
        visibility: str,
        required_level: str,
        allow_public: bool,
    ) -> None:
        """校验知识库访问权限。"""

        if allow_public and visibility == "public" and required_level == "read":
            return
        if current_user is None:
            raise AppError(
                code=ErrorCode.AUTH_UNAUTHORIZED,
                message="需要登录后访问",
                detail=None,
                status_code=401,
            )
        if "*" in current_user.permissions:
            return
        access = self._kb_access_repo.get(current_user.user.user_id, kb_id)
        if access and _has_level(access.access_level, required_level):
            return
        if visibility == "internal" and required_level == "read":
            return
        raise AppError(
            code=ErrorCode.KB_ACCESS_DENIED,
            message="无权访问该知识库",
            detail={"kb_id": kb_id},
            status_code=403,
        )


def _hash_token(token: str) -> str:
    """计算刷新令牌哈希。"""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _future_iso(days: int) -> str:
    """生成未来时间字符串。"""

    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(microsecond=0).isoformat()


def _is_expired(expires_at: str) -> bool:
    """判断是否过期。"""

    try:
        value = datetime.fromisoformat(expires_at)
    except ValueError:
        return True
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= datetime.now(timezone.utc)


def _has_level(actual: str, required: str) -> bool:
    """判断访问级别是否满足。"""

    order = {"read": 1, "write": 2, "admin": 3}
    return order.get(actual, 0) >= order.get(required, 0)


def _dump_permissions(permissions: list[str]) -> str:
    """序列化权限列表。"""

    return json.dumps(permissions, ensure_ascii=False)
