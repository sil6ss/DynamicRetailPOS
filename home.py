# Created by: Silas Young, Katie Southard, Alex Puckett, Mesh Young
# 03/2026 - 05/2026 Elevate Retail Capstone Class, Forsyth Tech Community College

from flask import Flask, render_template, request, redirect, url_for, session
from flask_login import LoginManager
from auth import auth_bp, User
from cart import cart_bp
from user import user_bp
from db import get_db_connection

# Initial setup, along with connection to database
home = Flask(__name__)
home.secret_key = "elevate-retail-secret-key"
home.register_blueprint(cart_bp)
home.register_blueprint(auth_bp)
home.register_blueprint(user_bp)

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.init_app(home)


# Retrieve all products from database containing fields necessary for webpage
def get_products():
    conn = get_db_connection()  # CHANGED: open a fresh connection for this function
    cursor = conn.cursor()  # CHANGED: create a fresh cursor for this function

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

    cursor.close()  # CHANGED: close cursor after query is done
    conn.close()  # CHANGED: close connection after query is done

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
    products = get_products()  # CHANGED: always reload products from DB so stock updates show immediately
    cart = session.get("cart", [])
    query = request.args.get("q", "").strip().lower()

    if query:
        filtered_products = [item for item in products if query in item["name"].lower()]  # CHANGED: search fresh DB data
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
    conn = get_db_connection()  # CHANGED: open a fresh connection when loading a user
    cursor = conn.cursor()  # CHANGED: create a fresh cursor when loading a user

    cursor.execute("""
        SELECT Customer_ID, First_Name, Last_Name, Email
        FROM Customer
        WHERE Customer_ID = %s
    """, (user_id,))
    row = cursor.fetchone()

    cursor.close()  # CHANGED: close cursor after query is done
    conn.close()  # CHANGED: close connection after query is done

    if row:
        return User(row[0], row[1], row[2], row[3])
    return None


if __name__ == "__main__":
    home.run(debug=True)