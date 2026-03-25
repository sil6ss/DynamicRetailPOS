import sqlite3

conn = sqlite3.connect("dynamic_retail_pos.db")
cursor = conn.cursor()

print("ORDERS:")
for row in cursor.execute("SELECT * FROM orders"):
    print(row)

print("\nORDER ITEMS:")
for row in cursor.execute("SELECT * FROM order_items"):
    print(row)

conn.close()