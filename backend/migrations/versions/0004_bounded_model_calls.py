"""Add durable model reservations and investigation stop metadata.

Revision ID: 0004_bounded_model_calls
Revises: 0003_reliable_jobs
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_bounded_model_calls"
down_revision = "0003_reliable_jobs"
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column("investigation_mode", sa.String(24), nullable=False, server_default="baseline"),
        sa.Column("stop_reason", sa.String(40), nullable=True),
        sa.Column("model_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved_model_cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
    ):
        op.add_column("jobs", column, schema="faultbrief")
    op.create_check_constraint(
        "ck_jobs_model_budget",
        "jobs",
        "model_call_count >= 0 AND reserved_model_cost_usd >= 0",
        schema="faultbrief",
    )
    op.create_check_constraint(
        "ck_jobs_investigation_mode",
        "jobs",
        "investigation_mode IN ('baseline', 'model_selected')",
        schema="faultbrief",
    )
    op.create_table(
        "model_calls",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("investigation_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(24), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("input_token_estimate", sa.Integer(), nullable=False),
        sa.Column("max_completion_tokens", sa.Integer(), nullable=False),
        sa.Column("reserved_cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_model_calls"),
        sa.UniqueConstraint("job_id", "sequence", name="uq_model_calls_job_id_sequence"),
        sa.ForeignKeyConstraint(
            ["job_id", "investigation_id", "workspace_id"],
            [
                "faultbrief.jobs.id",
                "faultbrief.jobs.investigation_id",
                "faultbrief.jobs.workspace_id",
            ],
            name="fk_model_calls_job_id_investigation_id_workspace_id_jobs",
        ),
        sa.CheckConstraint("purpose IN ('planner', 'explainer')", name="ck_model_calls_purpose"),
        sa.CheckConstraint(
            "state IN ('reserved', 'succeeded', 'failed')", name="ck_model_calls_state"
        ),
        sa.CheckConstraint(
            "attempt > 0 AND sequence > 0 AND input_token_estimate >= 0 "
            "AND max_completion_tokens > 0 AND reserved_cost_usd >= 0",
            name="ck_model_calls_budget_limits",
        ),
        schema="faultbrief",
    )


def downgrade():
    op.drop_table("model_calls", schema="faultbrief")
    for name in ("model_budget", "investigation_mode"):
        op.drop_constraint("ck_jobs_" + name, "jobs", schema="faultbrief", type_="check")
    for name in (
        "reserved_model_cost_usd",
        "model_call_count",
        "stop_reason",
        "investigation_mode",
    ):
        op.drop_column("jobs", name, schema="faultbrief")
