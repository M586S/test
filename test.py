import sqlite3

# Connect to a database (it will create the database file if it doesn't exist)
conn = sqlite3.connect('example.db')

# Create a cursor object to interact with the database
cursor = conn.cursor()

# Create a table
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT,
    age INTEGER
)
''')

# Insert some data into the table
#cursor.execute("INSERT INTO users (name, age) VALUES ('Alice', 30)")
#cursor.execute("INSERT INTO users (name, age) VALUES ('Bob', 25)")
#cursor.execute("INSERT INTO users (name, age) VALUES ('Charlie', 35)")

# Commit the changes to the database
#conn.commit()

# Select the data from the table
cursor.execute("SELECT * FROM users")

# Fetch all the rows
rows = cursor.fetchall()

# Print the data
print("Inserted Data:")
for row in rows:
    print(row)

# Close the connection
conn.close()
