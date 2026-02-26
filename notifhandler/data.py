import psycopg2

try:
    conn = psycopg2.connect(
        dbname="robocop",
        user="admin",
        password="Grey@123",
        host="localhost",
        port="5432"
    )
    print("Connected successfully!")
except Exception as e:
    print("Connection failed:", e)
