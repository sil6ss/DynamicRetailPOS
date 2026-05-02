from flask import Blueprint, render_template, request, redirect, url_for, session
from flask_login import login_required, current_user
import mysql.connector
from datetime import datetime
from db import get_db_connection

cart_bp = Blueprint("cart", __name__)
cart_bp.secret_key = "elevate-retail-secret-key"

#promo codes use flat dollar discounts
PROMO_CODES = {
    "NEW5": 5.00,
    "SAVE10": 10.00
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


# Calculates cart totals using the user's selected discount choice
def calculate_cart_totals(
    cart_items,
    promo_code=None,
    membership_rate=0.0,
    membership_upgrade_cost=0.0,
    discount_choice="none"
):
    subtotal = sum(item["price"] * item["quantity"] for item in cart_items)

    membership_discount = subtotal * membership_rate

    # Promo code discount: flat dollar amount
    promo_discount = 0.00
    if promo_code:
        promo_code = promo_code.upper().strip()
        promo_value = PROMO_CODES.get(promo_code)

        if isinstance(promo_value, (int, float)):
            promo_discount = min(float(promo_value), subtotal)

    # Automatic subtotal discount
    auto_discount = 0.00
    auto_discount_rate = 0.00
    auto_deal_message = ""

    if subtotal >= 300:
        auto_discount_rate = 0.20
        auto_discount = subtotal * auto_discount_rate
        auto_deal_message = "You unlocked 20% off with the automatic deal."
    elif subtotal >= 100:
        auto_discount_rate = 0.15
        auto_discount = subtotal * auto_discount_rate
        amount_to_next_discount = 300 - subtotal
        auto_deal_message = f"You unlocked 15% off. Add ${amount_to_next_discount:.2f} more to unlock 20% off."
    else:
        amount_to_next_discount = 100 - subtotal
        auto_deal_message = f"Add ${amount_to_next_discount:.2f} more to unlock 15% off automatically."

    # User-selected discount choice
    applied_discount_name = ""
    applied_discount_amount = 0.00

    if discount_choice == "promo" and promo_discount > 0:
        applied_discount_name = "Promo Discount"
        applied_discount_amount = promo_discount
    elif discount_choice == "auto" and auto_discount > 0:
        if auto_discount_rate == 0.20:
            applied_discount_name = "Automatic Discount (20%)"
        elif auto_discount_rate == 0.15:
            applied_discount_name = "Automatic Discount (15%)"
        else:
            applied_discount_name = "Automatic Discount"

        applied_discount_amount = auto_discount
    else:
        discount_choice = "none"

    discounted_subtotal = max(subtotal - membership_discount - applied_discount_amount, 0)

    tax_rate = 0.07
    sales_tax = discounted_subtotal * tax_rate

    # Shipping is kept at 0 in backend but no longer shown in the UI
    shipping = 0.00

    total = discounted_subtotal + sales_tax + shipping + membership_upgrade_cost

    return {
        "subtotal": subtotal,
        "membership_discount": membership_discount,
        "promo_discount": promo_discount,
        "auto_discount": auto_discount,
        "auto_discount_rate": auto_discount_rate,
        "auto_deal_message": auto_deal_message,
        "discount_choice": discount_choice,
        "applied_discount_name": applied_discount_name,
        "applied_discount_amount": applied_discount_amount,
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
    discount_choice = session.get("discount_choice", "none")
    cart_items = session.get("cart", [])

    current_level = get_current_membership_level(current_user.id)
    selected_level = session.get("selected_membership_level", current_level)

    membership_rate = get_membership_discount_rate(current_user.id)
    membership_upgrade_cost = calculate_membership_upgrade_cost(current_level, selected_level)

    totals = calculate_cart_totals(
        cart_items,
        promo_code,
        membership_rate,
        membership_upgrade_cost,
        discount_choice
    )

    recommendations = get_recommendations(cart_items)

    return render_template(
        "cart.html",
        cart=cart_items,
        subtotal=totals["subtotal"],
        membership_discount=totals["membership_discount"],
        promo_discount=totals["promo_discount"],
        auto_discount=totals["auto_discount"],
        auto_discount_rate=totals["auto_discount_rate"],
        auto_deal_message=totals["auto_deal_message"],
        discount_choice=totals["discount_choice"],
        applied_discount_name=totals["applied_discount_name"],
        applied_discount_amount=totals["applied_discount_amount"],
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


# Route to choose which discount should be applied
@cart_bp.route("/update_discount_choice", methods=["POST"])
@login_required
def update_discount_choice():
    discount_choice = request.form.get("discount_choice", "none")

    if discount_choice not in ["none", "promo", "auto"]:
        discount_choice = "none"

    session["discount_choice"] = discount_choice
    return redirect(url_for("cart.cart"))


# Route to item quantity update
@cart_bp.route("/update_cart", methods=["POST"])
@login_required
def update_cart():
    product_name = request.form["product_name"]
    quantity = int(request.form["quantity"])
    redirect_to = request.form.get("redirect_to", "cart")

    cart_items = session.get("cart", [])

    for item in cart_items:
        if item["name"] == product_name:
            if quantity > 0:
                item["quantity"] = quantity
            else:
                cart_items.remove(item)
            break

    session["cart"] = cart_items
    session.modified = True

    if redirect_to == "home":
        return redirect(url_for("home_page"))

    return redirect(url_for("cart.cart"))


# Route for promo
@cart_bp.route("/apply_promo", methods=["POST"])
@login_required
def apply_promo():
    promo_code = request.form.get("promo_code", "").strip().upper()

    if promo_code in PROMO_CODES:
        session["promo_code"] = promo_code
        session["discount_choice"] = "promo"
    else:
        session["promo_code"] = ""

        # If the user clears/enters an invalid promo, do not force promo discount
        if session.get("discount_choice") == "promo":
            session["discount_choice"] = "none"

    return redirect(url_for("cart.cart"))


# Route for completely removing item
@cart_bp.route("/remove_from_cart", methods=["POST"])
@login_required
def remove_from_cart():
    product_name = request.form["product_name"]
    redirect_to = request.form.get("redirect_to", "cart")

    cart_items = session.get("cart", [])

    cart_items = [item for item in cart_items if item["name"] != product_name]

    session["cart"] = cart_items
    session.modified = True

    if redirect_to == "home":
        return redirect(url_for("home_page"))

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
        session.modified = True

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
    session.pop("discount_choice", None)
    session.pop("selected_membership_level", None)
    return redirect(url_for("cart.cart"))


def get_customer_addresses(customer_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT Address_ID, Address_Line_l, Address_Line_2, City, State, Zip_Code, Country
        FROM Customer_Address
        WHERE Customer_ID = %s AND Deleted_At IS NULL
        ORDER BY Address_ID DESC
    """, (customer_id,))

    addresses = cursor.fetchall()

    cursor.close()
    conn.close()
    return addresses


@cart_bp.route("/payment")
@login_required
def payment():
    cart_items = session.get("cart", [])
    promo_code = session.get("promo_code", "")
    discount_choice = session.get("discount_choice", "none")

    current_level = get_current_membership_level(current_user.id)
    selected_level = session.get("selected_membership_level", current_level)

    membership_rate = get_membership_discount_rate(current_user.id)
    membership_upgrade_cost = calculate_membership_upgrade_cost(current_level, selected_level)

    # Allow payment page if there are cart items or a pending membership upgrade
    if not cart_items and membership_upgrade_cost <= 0:
        return redirect(url_for("cart.cart"))

    totals = calculate_cart_totals(
        cart_items,
        promo_code,
        membership_rate,
        membership_upgrade_cost,
        discount_choice
    )

    # Load all saved addresses for dropdown
    addresses = get_customer_addresses(current_user.id)

    # Use the newest saved address as the default one if there is one
    address = addresses[0] if addresses else None

    return render_template(
        "payment.html",
        cart=cart_items,
        subtotal=totals["subtotal"],
        membership_discount=totals["membership_discount"],
        promo_discount=totals["promo_discount"],
        auto_discount=totals["auto_discount"],
        auto_discount_rate=totals["auto_discount_rate"],
        auto_deal_message=totals["auto_deal_message"],
        discount_choice=totals["discount_choice"],
        applied_discount_name=totals["applied_discount_name"],
        applied_discount_amount=totals["applied_discount_amount"],
        membership_upgrade_cost=totals["membership_upgrade_cost"],
        sales_tax=totals["sales_tax"],
        shipping=totals["shipping"],
        total=totals["total"],
        promo_code=promo_code,
        current_membership_level=current_level,
        selected_membership_level=selected_level,
        address=address,
        addresses=addresses
    )


@cart_bp.route("/order_confirmation", methods=["POST"])
@login_required
def order_confirmation():
    promo_code = session.get("promo_code", "")
    discount_choice = session.get("discount_choice", "none")
    cart_items = session.get("cart", [])

    payment_method = request.form.get("payment_method", "N/A")

    # Carrier can come from a dropdown later. For now, default to UPS if nothing is sent.
    selected_carrier = request.form.get("carrier", "UPS").strip()
    if not selected_carrier:
        selected_carrier = "UPS"

    current_level = get_current_membership_level(current_user.id)
    selected_level = session.get("selected_membership_level", current_level)

    membership_rate = get_membership_discount_rate(current_user.id)
    membership_upgrade_cost = calculate_membership_upgrade_cost(current_level, selected_level)

    # Allow order confirmation if there are cart items or a pending membership upgrade
    if not cart_items and membership_upgrade_cost <= 0:
        return redirect(url_for("cart.cart"))

    totals = calculate_cart_totals(
        cart_items,
        promo_code,
        membership_rate,
        membership_upgrade_cost,
        discount_choice
    )

    # Use the submitted shipping address from the payment page
    address = {
        "Address_Line_l": request.form.get("address", "").strip(),
        "Address_Line_2": request.form.get("address2", "").strip(),
        "City": request.form.get("city", "").strip(),
        "State": request.form.get("state", "").strip(),
        "Zip_Code": request.form.get("zip", "").strip(),
        "Country": request.form.get("country", "").strip()
    }

    save_address = request.form.get("save_address") == "yes"

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. Make sure there is an address ID for Shipping.
        # Shipping table requires Shipping_Address_ID and Billing_Address_ID.
        shipping_address_id = None

        if (
            address["Address_Line_l"]
            and address["City"]
            and address["State"]
            and address["Zip_Code"]
            and address["Country"]
        ):
            cursor.execute("""
                SELECT Address_ID
                FROM Customer_Address
                WHERE Customer_ID = %s
                  AND Address_Line_l = %s
                  AND IFNULL(Address_Line_2, '') = %s
                  AND City = %s
                  AND State = %s
                  AND Zip_Code = %s
                  AND Country = %s
                  AND Deleted_At IS NULL
                LIMIT 1
            """, (
                current_user.id,
                address["Address_Line_l"],
                address["Address_Line_2"],
                address["City"],
                address["State"],
                address["Zip_Code"],
                address["Country"]
            ))

            existing_address = cursor.fetchone()

            if existing_address:
                shipping_address_id = existing_address[0]
            else:
                cursor.execute("""
                    INSERT INTO Customer_Address
                    (Address_Line_l, Address_Line_2, City, State, Zip_Code, Country, Customer_ID)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    address["Address_Line_l"],
                    address["Address_Line_2"] or None,
                    address["City"],
                    address["State"],
                    address["Zip_Code"],
                    address["Country"],
                    current_user.id
                ))

                shipping_address_id = cursor.lastrowid

        # If no address was submitted, try to use the newest saved address.
        if not shipping_address_id:
            cursor.execute("""
                SELECT Address_ID, Address_Line_l, Address_Line_2, City, State, Zip_Code, Country
                FROM Customer_Address
                WHERE Customer_ID = %s
                  AND Deleted_At IS NULL
                ORDER BY Address_ID DESC
                LIMIT 1
            """, (current_user.id,))

            saved_address = cursor.fetchone()

            if saved_address:
                shipping_address_id = saved_address[0]

                # Fill address info for the confirmation page if needed.
                address = {
                    "Address_Line_l": saved_address[1],
                    "Address_Line_2": saved_address[2],
                    "City": saved_address[3],
                    "State": saved_address[4],
                    "Zip_Code": saved_address[5],
                    "Country": saved_address[6]
                }

        # If there is still no address, stop checkout because Shipping requires it.
        if not shipping_address_id:
            conn.rollback()
            return "Database error: A shipping address is required to create a shipping record.", 500

        billing_address_id = shipping_address_id

        # 2. Insert order
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

        # 3. Insert order items
        subtotal = totals["subtotal"]
        discountable_subtotal = max(
            subtotal - totals["membership_discount"] - totals["applied_discount_amount"],
            0
        )
        sales_tax = totals["sales_tax"]

        order_items = []

        for item in cart_items:
            line_subtotal = item["price"] * item["quantity"]
            line_ratio = (line_subtotal / subtotal) if subtotal > 0 else 0
            line_amount = round(discountable_subtotal * line_ratio, 2)
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

        # 4. Insert payment
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

        # 5. Update order from Pending to Paid after payment is confirmed
        cursor.execute("""
            UPDATE `Order`
            SET Order_Status = %s
            WHERE Order_ID = %s
        """, (
            "Paid",
            order_id
        ))

        # 6. Create initial shipping row for shipping team.
        # Shipping can update this later with real status, shipped date, tracking, etc.
        cursor.execute("""
            INSERT INTO Shipping (
                Order_ID,
                Cost,
                Shipped_On,
                Expected_By,
                Ship_Status,
                Carrier,
                Tracking_Number,
                Shipping_Address_ID,
                Billing_Address_ID,
                Shipment_Notes,
                Return_Reason
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            order_id,
            0.00,
            None,
            None,
            "Pending",
            selected_carrier,
            "Pending",
            shipping_address_id,
            billing_address_id,
            "Shipping label not created yet.",
            None
        ))

        # 7. Update membership level if upgraded
        if selected_level != current_level:
            cursor.execute("""
                UPDATE Customer
                SET Membership_Level = %s,
                    Updated_At = UTC_TIMESTAMP()
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
            "auto_discount": totals["auto_discount"],
            "auto_deal_message": totals["auto_deal_message"],
            "discount_choice": totals["discount_choice"],
            "applied_discount_name": totals["applied_discount_name"],
            "applied_discount_amount": totals["applied_discount_amount"],
            "membership_upgrade_cost": totals["membership_upgrade_cost"],
            "tax": totals["sales_tax"],
            "total_paid": totals["total"],
            "carrier": selected_carrier
        }

        # Clear session
        session.pop("cart", None)
        session.pop("promo_code", None)
        session.pop("discount_choice", None)
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