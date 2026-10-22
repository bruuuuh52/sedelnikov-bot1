import sqlite3
conn = sqlite3.connect('data/screening.db')
cursor = conn.cursor()
cursor.execute('SELECT sql FROM sqlite_master WHERE type="table" AND name="screenings"')
result = cursor.fetchone()
print(result[0])