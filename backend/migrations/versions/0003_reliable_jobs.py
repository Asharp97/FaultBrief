"""Add submission replay protection and durable job progress.

Revision ID: 0003_reliable_jobs
Revises: 0002_investigation_reports
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_reliable_jobs"
down_revision = "0002_investigation_reports"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "investigations",
        sa.Column("submission_id", postgresql.UUID(), nullable=True),
        schema="faultbrief",
    )
    op.add_column(
        "investigations",
        sa.Column("submission_fingerprint", sa.String(64), nullable=True),
        schema="faultbrief",
    )
    op.create_unique_constraint(
        "uq_investigations_workspace_id_created_by_user_id_submission_id",
        "investigations",
        ["workspace_id", "created_by_user_id", "submission_id"],
        schema="faultbrief",
    )
    for column in [
        sa.Column("phase", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("completed_steps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(40), nullable=True),
    ]:
        op.add_column("jobs", column, schema="faultbrief")
    op.execute(
        "UPDATE faultbrief.jobs SET phase = CASE state WHEN 'running' THEN 'claimed' ELSE state END"
    )
    op.create_check_constraint(
        "ck_jobs_progress_limits",
        "jobs",
        "completed_steps >= 0 AND completed_steps <= 20",
        schema="faultbrief",
    )
    op.create_check_constraint(
        "ck_jobs_progress_phase",
        "jobs",
        "phase IN ('queued', 'claimed', 'collecting', 'explaining', 'publishing', "
        "'retry_wait', 'completed', 'failed')",
        schema="faultbrief",
    )


def downgrade():
    op.drop_constraint("ck_jobs_progress_phase", "jobs", schema="faultbrief", type_="check")
    op.drop_constraint("ck_jobs_progress_limits", "jobs", schema="faultbrief", type_="check")
    for name in ("last_error_code", "heartbeat_at", "completed_steps", "phase"):
        op.drop_column("jobs", name, schema="faultbrief")
    op.drop_constraint(
        "uq_investigations_workspace_id_created_by_user_id_submission_id",
        "investigations",
        schema="faultbrief",
        type_="unique",
    )
    for name in ("submission_fingerprint", "submission_id"):
        op.drop_column("investigations", name, schema="faultbrief")
