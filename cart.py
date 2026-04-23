from flask import Blueprint, render_template, request, redirect, url_for, session
from flask_login import login_required, current_user
import mysql.connector
from datetime import datetime
from db import get_db_connection

cart_bp = Blueprint("cart", __name__)
cart_bp.secret_key = "elevate-retail-secret-key"

# temp promo codes for testing
PROMO_CODES = {
    "SAVE10": 0.10,
    "SAVE20": 0.20,
    "NEW5": 0.05
}

MEMBERSHIP_PRICES = {
    "Bronze": 0,
    "Silver": 30,
    "Gold": 60,
    "Platinum": 100
}


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


def get_current_membership_level(customer_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT Membership_Level
        FROM Customer
        WHERE Customer_ID = %s
            AND Deleted_At IS NULL
    """, (customer_id,))
    row = cursor.fetchone()

    cursor.close()
    conn.close()

    if not row or row[0] is None:
        return "Bronze"

    return row[0]


def calculate_membership_upgrade_cost(current_level, selected_level):
    current_price = MEMBERSHIP_PRICES.get(current_level, 0)
    selected_price = MEMBERSHIP_PRICES.get(selected_level, 0)

    upgrade_cost = selected_price - current_price

    if upgrade_cost < 0:
        upgrade_cost = 0

    return upgrade_cost


# Calculates cart totals (membership, promo, tax, shipping, upgrade)
def calculate_cart_totals(cart_items, promo_code=None, membership_rate=0.0, membership_upgrade_cost=0.0):
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
    total = discounted_subtotal + sales_tax + shipping + membership_upgrade_cost

    return {
        "subtotal": subtotal,
        "membership_discount": membership_discount,
        "promo_discount": promo_discount,
        "membership_upgrade_cost": membership_upgrade_cost,
        "sales_tax": sales_tax,
        "shipping": shipping,
        "total": total,
        "discounted_subtotal": discounted_subtotal
    }


# Gets recommended products based on most purchased items
def get_recommendations(cart_items, limit=3):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cart_inventory_ids = [
            item["inventory_id"] for item in cart_items
            if "inventory_id" in item
        ]

        query = """
            SELECT
                i.Inventory_ID,
                p.Product_Name,
                p.Product_Description,
                p.Image_URL,
                i.Unit_Price,
                i.Quantity,
                COALESCE(SUM(oi.Quantity), 0) AS TotalPurchased
            FROM Inventory i
            JOIN Product p
                ON i.Product_ID = p.Product_ID
            LEFT JOIN Order_Item oi
                ON i.Inventory_ID = oi.Inventory_ID
            WHERE i.Quantity > 0
        """

        params = []

        if cart_inventory_ids:
            placeholders = ", ".join(["%s"] * len(cart_inventory_ids))
            query += f" AND i.Inventory_ID NOT IN ({placeholders}) "
            params.extend(cart_inventory_ids)

        query += """
            GROUP BY
                i.Inventory_ID,
                p.Product_Name,
                p.Product_Description,
                p.Image_URL,
                i.Unit_Price,
                i.Quantity
            ORDER BY TotalPurchased DESC, p.Product_Name ASC
            LIMIT %s
        """
        params.append(limit)

        cursor.execute(query, tuple(params))
        recommendations = cursor.fetchall()

        return recommendations

    except mysql.connector.Error as err:
        print(f"Recommendation query error: {err}")
        return []

    finally:
        cursor.close()
        conn.close()


# Cart page route
@cart_bp.route("/cart")
@login_required
def cart():
    if "cart" not in session:
        session["cart"] = []

    promo_code = session.get("promo_code", "")
    cart_items = session.get("cart", [])

    current_level = get_current_membership_level(current_user.id)
    selected_level = session.get("selected_membership_level", current_level)

    membership_rate = get_membership_discount_rate(current_user.id)
    membership_upgrade_cost = calculate_membership_upgrade_cost(current_level, selected_level)

    totals = calculate_cart_totals(
        cart_items,
        promo_code,
        membership_rate,
        membership_upgrade_cost
    )

    recommendations = get_recommendations(cart_items)

    return render_template(
        "cart.html",
        cart=cart_items,
        subtotal=totals["subtotal"],
        membership_discount=totals["membership_discount"],
        promo_discount=totals["promo_discount"],
        membership_upgrade_cost=totals["membership_upgrade_cost"],
        sales_tax=totals["sales_tax"],
        shipping=totals["shipping"],
        total=totals["total"],
        promo_code=promo_code,
        current_membership_level=current_level,
        selected_membership_level=selected_level,
        membership_prices=MEMBERSHIP_PRICES,
        recommendations=recommendations
    )


# Route to save selected membership level
@cart_bp.route("/update_membership", methods=["POST"])
@login_required
def update_membership():
    current_level = get_current_membership_level(current_user.id)
    selected_level = request.form.get("membership_level", current_level)

    if selected_level not in MEMBERSHIP_PRICES:
        selected_level = current_level

    session["selected_membership_level"] = selected_level
    return redirect(url_for("cart.cart"))


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


# Route to add recommended item to cart
@cart_bp.route("/add_recommended_to_cart", methods=["POST"])
@login_required
def add_recommended_to_cart():
    inventory_id = request.form.get("product_id")

    if not inventory_id:
        return redirect(url_for("cart.cart"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                i.Inventory_ID,
                p.Product_Name,
                p.Product_Description,
                p.Image_URL,
                i.Unit_Price,
                i.Quantity
            FROM Inventory i
            JOIN Product p
                ON i.Product_ID = p.Product_ID
            WHERE i.Inventory_ID = %s
                AND i.Quantity > 0
        """, (inventory_id,))

        product = cursor.fetchone()

        if not product:
            return redirect(url_for("cart.cart"))

        cart_items = session.get("cart", [])
        found = False

        for item in cart_items:
            if item.get("inventory_id") == product["Inventory_ID"]:
                item["quantity"] += 1
                found = True
                break

        if not found:
            cart_items.append({
                "inventory_id": product["Inventory_ID"],
                "name": product["Product_Name"],
                "description": product["Product_Description"],
                "price": float(product["Unit_Price"]),
                "quantity": 1,
                "image": product["Image_URL"]
            })

        session["cart"] = cart_items
        session.modified = True  # CHANGED: makes sure Flask saves the cart update

    except mysql.connector.Error as err:
        print(f"Add recommended item error: {err}")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("cart.cart"))


# Route to clear cart and reload
@cart_bp.route("/clear_cart")
@login_required
def clear_cart():
    session.pop("cart", None)
    session.pop("promo_code", None)
    session.pop("selected_membership_level", None)
    return redirect(url_for("cart.cart"))


@cart_bp.route("/payment")
@login_required
def payment():
    cart_items = session.get("cart", [])
    promo_code = session.get("promo_code", "")

    current_level = get_current_membership_level(current_user.id)
    selected_level = session.get("selected_membership_level", current_level)

    membership_rate = get_membership_discount_rate(current_user.id)
    membership_upgrade_cost = calculate_membership_upgrade_cost(current_level, selected_level)

    totals = calculate_cart_totals(
        cart_items,
        promo_code,
        membership_rate,
        membership_upgrade_cost
    )

    # Load customer address
    address = get_customer_address(current_user.id)

    return render_template(
        "payment.html",
        cart=cart_items,
        subtotal=totals["subtotal"],
        membership_discount=totals["membership_discount"],
        promo_discount=totals["promo_discount"],
        membership_upgrade_cost=totals["membership_upgrade_cost"],
        sales_tax=totals["sales_tax"],
        shipping=totals["shipping"],
        total=totals["total"],
        promo_code=promo_code,
        current_membership_level=current_level,
        selected_membership_level=selected_level,
        address=address
    )


def get_customer_address(customer_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT Address_Line_l, Address_Line_2, City, State, Zip_Code, Country
        FROM Customer_Address
        WHERE Customer_ID = %s AND Deleted_At IS NULL
        ORDER BY Created_At DESC
        LIMIT 1
    """, (customer_id,))

    address = cursor.fetchone()

    cursor.close()
    conn.close()
    return address


@cart_bp.route("/order_confirmation", methods=["POST"])
@login_required
def order_confirmation():
    promo_code = session.get("promo_code", "")
    cart_items = session.get("cart", [])

    if not cart_items:
        return redirect(url_for("cart.cart"))

    payment_method = request.form.get("payment_method", "N/A")

    current_level = get_current_membership_level(current_user.id)
    selected_level = session.get("selected_membership_level", current_level)

    membership_rate = get_membership_discount_rate(current_user.id)
    membership_upgrade_cost = calculate_membership_upgrade_cost(current_level, selected_level)

    totals = calculate_cart_totals(
        cart_items,
        promo_code,
        membership_rate,
        membership_upgrade_cost
    )

    # Load address for confirmation page
    address = get_customer_address(current_user.id)

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
            "Pending",
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

            cursor.execute("""
                UPDATE Inventory
                SET Quantity = Quantity - %s
                WHERE Inventory_ID = %s
            """, (
                item["quantity"],
                item["inventory_id"]
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
            "Completed",
            datetime.now(),
            datetime.now(),
            datetime.now()
        ))

        # 4. Update membership level if upgraded
        if selected_level != current_level:
            cursor.execute("""
                UPDATE Customer
                SET Membership_Level = %s
                WHERE Customer_ID = %s
            """, (selected_level, current_user.id))

        conn.commit()

        order = {
            "order_number": order_id,
            "date": datetime.now().strftime("%B %d, %Y"),
            "customer_name": f"{current_user.first_name} {current_user.last_name}",
            "payment_method": payment_method,
            "subtotal": totals["subtotal"],
            "membership_discount": totals["membership_discount"],
            "promo_discount": totals["promo_discount"],
            "membership_upgrade_cost": totals["membership_upgrade_cost"],
            "tax": totals["sales_tax"],
            "total_paid": totals["total"]
        }

        # Clear session
        session.pop("cart", None)
        session.pop("promo_code", None)
        session.pop("selected_membership_level", None)

        return render_template(
            "order_confirmation.html",
            order=order,
            order_items=order_items,
            address=address
        )

    except mysql.connector.Error as err:
        conn.rollback()
        return f"Database error: {err}", 500

    finally:
        cursor.close()
        conn.close()