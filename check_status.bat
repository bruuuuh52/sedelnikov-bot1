@echo off
cd /d C:\Users\Алина\Documents\sedelnikov_bot
C:\Users\Алина\Documents\sedelnikov_bot\venv\Scripts\python.exe -c "
import sqlite3
conn = sqlite3.connect('data/screening.db')
c = conn.cursor()
c.execute('SELECT DISTINCT status FROM screenings')
print('Statuses:', c.fetchall())
"