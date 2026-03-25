import sqlite3
from datetime import datetime

# =========================
# Dynamic Retail Solutions
# POS System with Database
# =========================

# Connect to SQLite database
conn = sqlite3.connect("dynamic_retail_pos.db")
cursor = conn.cursor()

# Create tables
cursor.execute("""
CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    price REAL NOT NULL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_date TEXT NOT NULL,
    total REAL NOT NULL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS order_items (
    order_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    product_name TEXT NOT NULL,
    price REAL NOT NULL,
    quantity INTEGER NOT NULL,
    line_total REAL NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
)
""")

conn.commit()

# Product data
products = {
    1: {"name": "Hello World Tee", "price": 24.99},
    2: {"name": "404 Sleep Not Found Tee", "price": 26.99},
    3: {"name": "I Speak Python Tee", "price": 25.99},
    4: {"name": "Ctrl C Ctrl V Tee", "price": 27.99},
    5: {"name": "Code Sleep Repeat Tee", "price": 24.99}
}

# Insert products into database if not already there
for product_id, item in products.items():
    cursor.execute("""
    INSERT OR IGNORE INTO products (product_id, name, price)
    VALUES (?, ?, ?)
    """, (product_id, item["name"], item["price"]))

conn.commit()

cart = []

print("========================================")
print(" Dynamic Retail Solutions POS System ")
print("========================================")

while True:
    print("\nAvailable Tees:")
    for key, item in products.items():
        print(f"{key}. {item['name']} - ${item['price']:.2f}")

    print("6. Checkout")
    print("7. Exit")

    try:
        choice = int(input("\nSelect an option: "))
    except ValueError:
        print("Please enter a valid number.")
        continue

    if choice in products:
        try:
            quantity = int(input("Enter quantity: "))
            if quantity <= 0:
                print("Quantity must be at least 1.")
                continue
        except ValueError:
            print("Please enter a valid quantity.")
            continue

        cart.append({
            "product_id": choice,
            "name": products[choice]["name"],
            "price": products[choice]["price"],
            "quantity": quantity
        })
        print(f"Added {quantity} x {products[choice]['name']} to cart.")

    elif choice == 6:
        if not cart:
            print("\nYour cart is empty.")
            continue

        print("\nYour Cart:")
        total = 0

        for item in cart:
            line_total = item["price"] * item["quantity"]
            total += line_total
            print(f"- {item['name']} | Qty: {item['quantity']} | ${line_total:.2f}")

        print(f"\nTotal: ${total:.2f}")

        # Save order
        order_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
        INSERT INTO orders (order_date, total)
        VALUES (?, ?)
        """, (order_date, total))

        order_id = cursor.lastrowid

        for item in cart:
            line_total = item["price"] * item["quantity"]
            cursor.execute("""
            INSERT INTO order_items (
                order_id, product_id, product_name, price, quantity, line_total
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """, (
                order_id,
                item["product_id"],
                item["name"],
                item["price"],
                item["quantity"],
                line_total
            ))

        conn.commit()

        print(f"\nOrder #{order_id} saved to database.")
        print("Thank you for shopping with Dynamic Retail Solutions.")

        cart.clear()

    elif choice == 7:
        print("Exiting system...")
        break

    else:
        print("Invalid option.")

conn.close()