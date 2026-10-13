"""Add ticket references and structured report facts/next steps.

Revision ID: 0002_investigation_reports
Revises: 0001_scoped_model
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_investigation_reports"
down_revision = "0001_scoped_model"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "investigations",
        sa.Column(
            "context", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        schema="faultbrief",
    )
    for name in ("observed_facts", "next_steps"):
        op.add_column(
            "reports",
            sa.Column(
                name, postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
            ),
            schema="faultbrief",
        )
    op.add_column(
        "reports",
        sa.Column("explanation_source", sa.String(24), server_default="rules", nullable=False),
        schema="faultbrief",
    )
    op.create_check_constraint(
        "ck_reports_explanation_source",
        "reports",
        "explanation_source IN ('rules', 'model', 'rules_fallback')",
        schema="faultbrief",
    )


def downgrade():
    op.drop_constraint(
        "ck_reports_explanation_source", "reports", type_="check", schema="faultbrief"
    )
    for name in ("explanation_source", "next_steps", "observed_facts"):
        op.drop_column("reports", name, schema="faultbrief")
    op.drop_column("investigations", "context", schema="faultbrief")
