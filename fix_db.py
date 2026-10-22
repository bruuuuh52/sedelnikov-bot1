import sqlite3

conn = sqlite3.connect('data/screening.db')
cursor = conn.cursor()

# Check current status values
cursor.execute('SELECT DISTINCT status FROM screenings')
print('Before:', cursor.fetchall())

# Disable foreign keys temporarily
cursor.execute('PRAGMA foreign_keys = OFF')

# Drop temp tables if they exist
cursor.execute('DROP TABLE IF EXISTS screenings_new')
cursor.execute('DROP TABLE IF EXISTS screenings_old')

# Create new table without CHECK constraint temporarily
cursor.execute('''
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
cursor.execute('''
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
cursor.execute('DROP TABLE screenings')
cursor.execute('ALTER TABLE screenings_new RENAME TO screenings')

# Recreate index
cursor.execute('CREATE INDEX ix_screenings_status ON screenings (status)')

# Verify
cursor.execute('SELECT DISTINCT status FROM screenings')
print('Statuses after:', cursor.fetchall())
print('Done!')