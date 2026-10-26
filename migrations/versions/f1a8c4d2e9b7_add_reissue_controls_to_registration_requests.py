"""Add reissue controls and limits to registration requests.

Revision ID: f1a8c4d2e9b7
Revises: e8c91a2d3b45
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1a8c4d2e9b7"
down_revision: str | Sequence[str] | None = "e8c91a2d3b45"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "auth_registration_requests",
        sa.Column(
            "reissue_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "auth_registration_requests",
        sa.Column(
            "last_reissue_idempotency_key",
            sa.String(length=128),
            nullable=True,
        ),
    )
    op.add_column(
        "auth_registration_requests",
        sa.Column(
            "current_invitation_id",
            sa.BigInteger(),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_auth_registration_requests_current_invitation_id",
        "auth_registration_requests",
        "auth_invitations",
        ["current_invitation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_auth_registration_requests_reissue_count",
        "auth_registration_requests",
        "reissue_count >= 0 AND reissue_count <= 3",
    )
    op.create_index(
        "ix_auth_registration_requests_last_reissue_key",
        "auth_registration_requests",
        ["last_reissue_idempotency_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_auth_registration_requests_last_reissue_key",
        table_name="auth_registration_requests",
    )
    op.drop_constraint(
        "ck_auth_registration_requests_reissue_count",
        "auth_registration_requests",
        type_="check",
    )
    op.drop_constraint(
        "fk_auth_registration_requests_current_invitation_id",
        "auth_registration_requests",
        type_="foreignkey",
    )
    op.drop_column("auth_registration_requests", "current_invitation_id")
    op.drop_column("auth_registration_requests", "last_reissue_idempotency_key")
    op.drop_column("auth_registration_requests", "reissue_count")
