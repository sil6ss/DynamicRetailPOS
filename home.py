# Created by: Silas Young, Katie Southard, Alex Puckett, Mesh Young
# 03/2026 - 05/2026 Elevate Retail Capstone Class, Forsyth Tech Community College

from flask import Flask, render_template, request, redirect, url_for, session
from flask_login import LoginManager
from auth import auth_bp, User
import mysql.connector
from cart import cart_bp
from user import user_bp
import atexit
import os
from dotenv import load_dotenv


# Initial setup, along with connection to database
home = Flask(__name__)
home.secret_key = "elevate-retail-secret-key"
home.register_blueprint(cart_bp)
home.register_blueprint(auth_bp)
home.register_blueprint(user_bp)

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.init_app(home)

load_dotenv()
host = os.getenv("DB_HOST")
user = os.getenv("DB_USER")
port = os.getenv("DB_PORT")
passw = os.getenv("DB_PASS")
db = os.getenv("DB_NAME")

conn = mysql.connector.connect(
    host=host,
    port=port,
    user=user,
    password=passw,
    database=db
)

cursor = conn.cursor()

if conn.is_connected():
    print("Connection Successful!")
else:
    print("Connection Failed.")


# Retrieve all products from database containing fields necessary for webpage
def get_products():
    cursor.execute("""
        SELECT
            Inventory.Inventory_ID,
            Product.Product_Name,
            Product.Product_Description,
            Product_Category.Category_Name,
            Inventory.Unit_Price,
            Product.Image_URL,
            Inventory.Quantity
        FROM Product
        INNER JOIN Inventory
            ON Product.Product_ID = Inventory.Product_ID
        INNER JOIN Product_Category
            ON Product.Category_ID = Product_Category.Category_ID
    """)
    sql_products = cursor.fetchall()
    return_products = []

    for item in sql_products:
        return_products.append({
            "inventory_id": item[0],
            "name": item[1],
            "description": item[2],
            "price": float(item[4]),
            "quantity": item[6],
            "image": item[5],
        })
    return return_products


# Base home page, with lists for the retrieved products and an empty cart for the user to use across the pages
@home.route("/")
def home_page():
    if "products" not in session or not session["products"]:
        session["products"] = get_products()

    products = session.get("products", [])
    cart = session.get("cart", [])
    query = request.args.get("q", "").strip().lower()

    if query:
        filtered_products = [item for item in session["products"] if query in item["name"].lower()]
    else:
        filtered_products = products

    return render_template(
        "home.html",
        products=filtered_products,
        cart=cart
    )


# Adds products to cart when clicked upon
@home.route("/add_cart", methods=["POST"])
def add_to_cart():
    if "cart" not in session:
        session["cart"] = []

    cart = session.get("cart", [])

    product = {
        "inventory_id": int(request.form.get("inventory_id")),
        "name": request.form.get("name"),
        "description": request.form.get("description"),
        "price": float(request.form.get("price", 0)),
        "image": request.form.get("image"),
        "quantity": 1
    }

    for item in cart:
        if item["inventory_id"] == product["inventory_id"]:
            item["quantity"] += 1
            session["cart"] = cart
            session.modified = True
            return redirect(url_for("home_page"))

    cart.append(product)
    session["cart"] = cart
    session.modified = True
    return redirect(url_for("home_page"))


@login_manager.user_loader
def load_user(user_id):
    cursor.execute("""
        SELECT Customer_ID, First_Name, Last_Name, Email
        FROM Customer
        WHERE Customer_ID = %s
    """, (user_id,))
    row = cursor.fetchone()
    if row:
        return User(row[0], row[1], row[2], row[3])
    return None


# Close connection to database to prevent errors
def cleanup():
    if conn.is_connected():
        conn.close()
        if conn.is_connected() is False:
            print("Connection Closed")


atexit.register(cleanup)

if __name__ == "__main__":
    home.run(debug=True)