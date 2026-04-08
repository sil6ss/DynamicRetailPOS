from flask import Flask, render_template, request, redirect, url_for, session
import mysql.connector
from cart import cart_bp
import atexit
import os
from dotenv import load_dotenv

home = Flask(__name__)
home.secret_key = "elevate-retail-secret-key"
home.register_blueprint(cart_bp)
load_dotenv()
host = os.getenv("HOST")
user= os.getenv("USER")
passw = os.getenv("PASS")
db = os.getenv("DATA")

conn = mysql.connector.connect(host=host, user=user, password=passw, database=db)

cursor = conn.cursor()

if conn.is_connected():
    print("Connection Successful!")
else:
    print("Connection Failed.")


def get_products():
    cursor.execute(""" SELECT Product.Product_Name, Product.Product_Description, Product_Category.Category_Name, Inventory.Unit_Price, Product.Image_URL, Inventory.Quantity
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
            "name": item[0],
            "description": item[1],
            "price": float(item[3]),
            "quantity": item[5],
            "image": item[4],
        })
    return return_products


@home.route("/")
def home_page():
    if "products" not in session or not session["products"]:
        session["products"] = get_products()

    products = session.get("products", [])
    cart = session.get("cart", [])
    return render_template(
        "home.html",
        products=products,
        cart=cart
    )

@home.route("/add_cart", methods=["POST"])
def add_to_cart():
    if "cart" not in session:  # temp data
        session["cart"] = []

    cart = session.get("cart", [])

    product = {
        "name": request.form.get("name"),
        "description": request.form.get("description"),
        "price": float(request.form.get("price")),
        "image": request.form.get("image"),
        "quantity": 1
    }

    for item in cart:
        if item["name"] == product["name"]:
            item["quantity"] += 1
            session["cart"] = cart
            session.modified = True
            return redirect(url_for("home_page"))
    cart.append(product)
    session["cart"] = cart
    session.modified = True
    return redirect(url_for("home_page"))


def cleanup():
    if conn.is_connected():
        conn.close()
        if conn.is_connected() is False:
            print("Connection Closed")
atexit.register(cleanup)

if __name__ == "__main__":
    home.run(debug=True)

