import mysql.connector

# Database connection and test.

conn = mysql.connector.connect(
    host="50.6.18.240",
    user="ukjirumy_er_app",
    password="dbPa$$Capstone26",
    database="ukjirumy_ElevateRetail",
    port="3306"
    )

cursor = conn.cursor()

if conn.is_connected():
    print("Connected to database successfully.")
else:
    print("Failed to connect to database.")