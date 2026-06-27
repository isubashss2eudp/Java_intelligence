from __future__ import annotations

"""Phase 9: Services sub-package."""

from src.platform.services.audit_service import log as audit_log, get_logs as get_audit_logs
from src.platform.services.user_service import (
    authenticate, create_user, get_user_by_username, get_user_by_id,
    get_user_or_404, list_users, update_user, change_password,
    update_role, deactivate_user,
)
from src.platform.services.repository_service import (
    create_repository, get_repository, get_repository_or_404,
    list_repositories, update_repository, delete_repository,
    assert_can_read, assert_can_write, grant_access, revoke_access,
    repo_data_dir, repo_metadata_path, repo_review_path, repo_onboarding_path,
)

__all__ = [
    "audit_log", "get_audit_logs",
    "authenticate", "create_user", "get_user_by_username", "get_user_by_id",
    "get_user_or_404", "list_users", "update_user", "change_password",
    "update_role", "deactivate_user",
    "create_repository", "get_repository", "get_repository_or_404",
    "list_repositories", "update_repository", "delete_repository",
    "assert_can_read", "assert_can_write", "grant_access", "revoke_access",
    "repo_data_dir", "repo_metadata_path", "repo_review_path", "repo_onboarding_path",
]
