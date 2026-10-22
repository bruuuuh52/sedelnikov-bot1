@echo off
cd /d C:\Users\Алина\Documents\sedelnikov_bot
C:\Users\Алина\Documents\sedelnikov_bot\venv\Scripts\python.exe -c "
import sqlite3
conn = sqlite3.connect('data/screening.db')
c = conn.cursor()

# Check current status values
c.execute('SELECT DISTINCT status FROM screenings')
print('Before:', c.fetchall())

# Disable foreign keys temporarily
c.execute('PRAGMA foreign_keys = OFF')

# Drop temp tables if they exist
c.execute('DROP TABLE IF EXISTS screenings_new')
c.execute('DROP TABLE IF EXISTS screenings_old')

# Create new table without CHECK constraint temporarily
c.execute('''
    CREATE TABLE screenings_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id INTEGER NOT NULL,
        vacancy_id INTEGER,
        interview_slot_id INTEGER,
        experience_years INTEGER,
        stack TEXT,
        salary_expectation INTEGER,
        relocation VARCHAR(50),
        portfolio_url VARCHAR(500),
        free_evenings VARCHAR(50),
        status VARCHAR(20) NOT NULL DEFAULT 'in_progress',
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        completed_at DATETIME,
        UNIQUE(candidate_id, vacancy_id)
    )
''')

# Copy data with uppercase status
c.execute('''
    INSERT INTO screenings_new (id, candidate_id, vacancy_id, interview_slot_id, experience_years, stack, salary_expectation, relocation, portfolio_url, free_evenies, status, created_at, updated_at, completed_at)
    SELECT id, candidate_id, vacancy_id, interview_slot_id, experience_years, stack, salary_expectation, relocation, portfolio_url, free_evenies,
        CASE 
            WHEN UPPER(status) = 'COMPLETED' THEN 'completed'
            WHEN UPPER(status) = 'IN_PROGRESS' THEN 'in_progress'
            WHEN UPPER(status) = 'REJECTED' THEN 'rejected'
            WHEN UPPER(status) = 'PENDING_ADMIN' THEN 'pending_admin'
            ELSE UPPER(status)
        END,
        created_at, updated_at, completed_at
    FROM screenings
''')

# Drop old table and rename
c.execute('DROP TABLE screenings')
c.execute('ALTER TABLE screenings_new RENAME TO screenings')

# Recreate index
c.execute('CREATE INDEX ix_screenings_status ON screenings (status)')

# Verify
c.execute('SELECT DISTINCT status FROM screenings')
print('Statuses after:', c.fetchall())
print('Done!')