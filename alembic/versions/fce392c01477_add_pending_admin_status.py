"""Add PENDING_ADMIN status

Revision ID: fce392c01477
Revises: 94efb581b90e
Create Date: 2026-10-22 12:12:52.895745

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fce392c01477'
down_revision: Union[str, Sequence[str], None] = '94efb581b90e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # SQLite doesn't support ALTER COLUMN for ENUM, so we need to recreate the table
    op.execute("""
        CREATE TABLE screenings_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
            vacancy_id INTEGER REFERENCES vacancies(id) ON DELETE SET NULL,
            interview_slot_id INTEGER REFERENCES interview_slots(id) ON DELETE SET NULL,
            experience_years INTEGER,
            stack TEXT,
            salary_expectation INTEGER,
            relocation VARCHAR(50),
            portfolio_url VARCHAR(500),
            free_evenings VARCHAR(50),
            status VARCHAR(20) NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress', 'pending_admin', 'completed', 'rejected')),
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            UNIQUE(candidate_id, vacancy_id)
        )
    """)
    
    # Copy data - map old statuses to new ones
    op.execute("""
        INSERT INTO screenings_new (id, candidate_id, vacancy_id, interview_slot_id, experience_years, stack, salary_expectation, relocation, portfolio_url, free_evenings, status, created_at, updated_at, completed_at)
        SELECT id, candidate_id, vacancy_id, interview_slot_id, experience_years, stack, salary_expectation, relocation, portfolio_url, free_evenings, 
            CASE 
                WHEN status = 'COMPLETED' THEN 'completed'
                WHEN status = 'IN_PROGRESS' THEN 'in_progress'
                ELSE status
            END,
            created_at, updated_at, completed_at
        FROM screenings
    """)
    
    # Drop old table and rename
    op.execute("DROP TABLE screenings")
    op.execute("ALTER TABLE screenings_new RENAME TO screenings")
    
    # Recreate indexes
    op.create_index('ix_screenings_candidate_id', 'screenings', ['candidate_id'])
    op.create_index('ix_screenings_vacancy_id', 'screenings', ['vacancy_id'])
    op.create_index('ix_screenings_interview_slot_id', 'screenings', ['interview_slot_id'])
    op.create_index('ix_screenings_status', 'screenings', ['status'])


def downgrade() -> None:
    """Downgrade schema."""
    # Recreate old table without PENDING_ADMIN
    op.execute("""
        CREATE TABLE screenings_old (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
            vacancy_id INTEGER REFERENCES vacancies(id) ON DELETE SET NULL,
            interview_slot_id INTEGER REFERENCES interview_slots(id) ON DELETE SET NULL,
            experience_years INTEGER,
            stack TEXT,
            salary_expectation INTEGER,
            relocation VARCHAR(50),
            portfolio_url VARCHAR(500),
            free_evenings VARCHAR(50),
            status VARCHAR(11) NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress', 'completed', 'rejected')),
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            UNIQUE(candidate_id, vacancy_id)
        )
    """)
    
    op.execute("""
        INSERT INTO screenings_old (id, candidate_id, vacancy_id, interview_slot_id, experience_years, stack, salary_expectation, relocation, portfolio_url, free_evenings, status, created_at, updated_at, completed_at)
        SELECT id, candidate_id, vacancy_id, interview_slot_id, experience_years, stack, salary_expectation, relocation, portfolio_url, free_evenings, 
            CASE 
                WHEN status = 'pending_admin' THEN 'in_progress'
                ELSE status
            END,
            created_at, updated_at, completed_at
        FROM screenings
    """)
    
    op.execute("DROP TABLE screenings")
    op.execute("ALTER TABLE screenings_old RENAME TO screenings")
    
    # Recreate indexes
    op.create_index('ix_screenings_candidate_id', 'screenings', ['candidate_id'])
    op.create_index('ix_screenings_vacancy_id', 'screenings', ['vacancy_id'])
    op.create_index('ix_screenings_interview_slot_id', 'screenings', ['interview_slot_id'])
    op.create_index('ix_screenings_status', 'screenings', ['status'])