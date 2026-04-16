from flask import Blueprint, render_template, request, redirect, url_for, session
from flask_login import login_required, current_user
import mysql.connector
from datetime import datetime

cart_bp = Blueprint("cart", __name__)
cart_bp.secret_key = "elevate-retail-secret-key"

# temp promo codes for testing
PROMO_CODES = {
    "SAVE10": 0.10,
    "SAVE20": 0.20,
    "NEW5": 5.00
}


def get_db_connection():
    from home import host, user, passw, db
    return mysql.connector.connect(
        host=host,
        user=user,
        password=passw,
        database=db
    )


def get_membership_discount_rate(customer_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT m.Discount_Rate
        FROM Customer c
        LEFT JOIN Member m
            ON c.Membership_Level = m.Membership_Level
        WHERE c.Customer_ID = %s
          AND c.Deleted_At IS NULL
    """, (customer_id,))
    row = cursor.fetchone()

    cursor.close()
    conn.close()

    if not row or row[0] is None:
        return 0.0

    rate = float(row[0])

    # If DB stores 10 for 10%, convert to 0.10
    if rate > 1:
        rate = rate / 100.0

    return rate


# Calculates cart totals (membership, promo, tax, shipping)
def calculate_cart_totals(cart_items, promo_code=None, membership_rate=0.0):
    subtotal = sum(item["price"] * item["quantity"] for item in cart_items)

    membership_discount = subtotal * membership_rate

    promo_discount = 0.00
    if promo_code:
        promo_code = promo_code.upper().strip()
        promo_value = PROMO_CODES.get(promo_code)

        if isinstance(promo_value, float) and promo_value < 1:
            promo_discount = subtotal * promo_value
        elif isinstance(promo_value, (int, float)):
            promo_discount = float(promo_value)

    discounted_subtotal = max(subtotal - membership_discount - promo_discount, 0)
    tax_rate = 0.07
    sales_tax = discounted_subtotal * tax_rate
    shipping = 0.00
    total = discounted_subtotal + sales_tax + shipping

    return {
        "subtotal": subtotal,
        "membership_discount": membership_discount,
        "promo_discount": promo_discount,
        "sales_tax": sales_tax,
        "shipping": shipping,
        "total": total,
        "discounted_subtotal": discounted_subtotal
    }


# Cart page route
@cart_bp.route("/cart")
@login_required
def cart():
    if "cart" not in session:
        session["cart"] = []

    promo_code = session.get("promo_code", "")
    cart_items = session.get("cart", [])
    membership_rate = get_membership_discount_rate(current_user.id)

    totals = calculate_cart_totals(
        cart_items,
        promo_code,
        membership_rate
    )

    return render_template(
        "cart.html",
        cart=cart_items,
        subtotal=totals["subtotal"],
        membership_discount=totals["membership_discount"],
        promo_discount=totals["promo_discount"],
        sales_tax=totals["sales_tax"],
        shipping=totals["shipping"],
        total=totals["total"],
        promo_code=promo_code
    )


# Route to item quantity update
@cart_bp.route("/update_cart", methods=["POST"])
@login_required
def update_cart():
    product_name = request.form["product_name"]
    quantity = int(request.form["quantity"])

    cart_items = session.get("cart", [])

    for item in cart_items:
        if item["name"] == product_name:
            if quantity > 0:
                item["quantity"] = quantity
            else:
                cart_items.remove(item)
            break

    session["cart"] = cart_items
    return redirect(url_for("cart.cart"))


# Route for promo
@cart_bp.route("/apply_promo", methods=["POST"])
@login_required
def apply_promo():
    promo_code = request.form.get("promo_code", "").strip().upper()

    if promo_code in PROMO_CODES:
        session["promo_code"] = promo_code
    else:
        session["promo_code"] = ""

    return redirect(url_for("cart.cart"))


# Route for completely removing item
@cart_bp.route("/remove_from_cart", methods=["POST"])
@login_required
def remove_from_cart():
    product_name = request.form["product_name"]
    cart_items = session.get("cart", [])

    cart_items = [item for item in cart_items if item["name"] != product_name]

    session["cart"] = cart_items
    return redirect(url_for("cart.cart"))


# Route to clear cart and reload
@cart_bp.route("/clear_cart")
@login_required
def clear_cart():
    session.pop("cart", None)
    session.pop("promo_code", None)
    return redirect(url_for("cart.cart"))


@cart_bp.route("/payment")
@login_required
def payment():
    cart_items = session.get("cart", [])
    promo_code = session.get("promo_code", "")
    membership_rate = get_membership_discount_rate(current_user.id)

    totals = calculate_cart_totals(
        cart_items,
        promo_code,
        membership_rate
    )

    return render_template(
        "payment.html",
        cart=cart_items,
        subtotal=totals["subtotal"],
        membership_discount=totals["membership_discount"],
        promo_discount=totals["promo_discount"],
        sales_tax=totals["sales_tax"],
        shipping=totals["shipping"],
        total=totals["total"],
        promo_code=promo_code
    )


@cart_bp.route("/order_confirmation", methods=["POST"])
@login_required
def order_confirmation():
    promo_code = session.get("promo_code", "")
    cart_items = session.get("cart", [])

    if not cart_items:
        return redirect(url_for("cart.cart"))

    payment_method = request.form.get("payment_method", "N/A")
    membership_rate = get_membership_discount_rate(current_user.id)

    totals = calculate_cart_totals(
        cart_items,
        promo_code,
        membership_rate
    )

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. Insert order
        cursor.execute("""
            INSERT INTO `Order` (
                Customer_ID,
                Order_Date,
                Order_Status,
                Fulfillment_Status,
                Fulfilled_At
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (
            current_user.id,
            datetime.now(),
            "Placed",
            "Pending",
            None
        ))

        order_id = cursor.lastrowid

        # 2. Insert order items
        subtotal = totals["subtotal"]
        discounted_subtotal = totals["discounted_subtotal"]
        sales_tax = totals["sales_tax"]

        order_items = []

        for item in cart_items:
            line_subtotal = item["price"] * item["quantity"]
            line_ratio = (line_subtotal / subtotal) if subtotal > 0 else 0
            line_amount = round(discounted_subtotal * line_ratio, 2)
            line_tax = round(sales_tax * line_ratio, 2)

            cursor.execute("""
                INSERT INTO Order_Item (
                    Order_ID,
                    Inventory_ID,
                    Quantity,
                    Amount,
                    Tax,
                    Created_At,
                    Updated_At
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                order_id,
                item["inventory_id"],
                item["quantity"],
                line_amount,
                line_tax,
                datetime.now(),
                datetime.now()
            ))

            order_items.append({
                "image_url": item["image"],
                "product_name": item["name"],
                "description": item["description"],
                "quantity": item["quantity"],
                "line_total": round(line_amount + line_tax, 2)
            })

        # 3. Insert payment
        cursor.execute("""
            INSERT INTO Payment (
                Order_ID,
                Method,
                Payment_Status,
                Created_At,
                Updated_At,
                Payment_Confirmed_At
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            order_id,
            payment_method,
            "Confirmed",
            datetime.now(),
            datetime.now(),
            datetime.now()
        ))

        conn.commit()

        order = {
            "order_number": order_id,
            "date": datetime.now().strftime("%B %d, %Y"),
            "customer_name": f"{current_user.first_name} {current_user.last_name}",
            "payment_method": payment_method,
            "subtotal": totals["subtotal"],
            "membership_discount": totals["membership_discount"],
            "promo_discount": totals["promo_discount"],
            "tax": totals["sales_tax"],
            "total_paid": totals["total"]
        }

        session.pop("cart", None)
        session.pop("promo_code", None)

        return render_template(
            "order_confirmation.html",
            order=order,
            order_items=order_items
        )

    except mysql.connector.Error as err:
        conn.rollback()
        return f"Database error: {err}", 500

    finally:
        cursor.close()
        conn.close()