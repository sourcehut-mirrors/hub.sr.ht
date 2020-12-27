"""Make source repo unique by project

Revision ID: 9deca12b2917
Revises: 4da86bb54214
Create Date: 2020-12-27 15:10:57.823055

"""

# revision identifiers, used by Alembic.
revision = '9deca12b2917'
down_revision = '4da86bb54214'

from alembic import op


def upgrade():
    # Drop duplicate source_repo keeping the latest.
    op.execute(
        "DELETE FROM source_repo A"
        " USING source_repo B"
        " WHERE A.project_id = B.project_id AND A.remote_id = B.remote_id"
        " AND A.repo_type = B.repo_type AND A.id < B.id;"
    )
    op.create_unique_constraint(
        "project_source_repo_unique",
        "source_repo",
        ["project_id", "remote_id", "repo_type"],
    )


def downgrade():
    op.drop_constraint("project_source_repo_unique", "source_repo", type_="unique")
