import sqlite3
conn = sqlite3.connect('data/screening.db')
c = conn.cursor()
c.execute('SELECT DISTINCT status FROM screenings')
print('Statuses:', c.fetchall())
conn.close()