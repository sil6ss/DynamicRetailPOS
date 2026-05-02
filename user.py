from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from db import get_db_connection
import random
import string

user_bp = Blueprint('user', __name__)
user_bp.secret_key = "elevate-retail-secret-key"


@user_bp.route('/profile')
@login_required
def profile():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT First_Name, Last_Name, Email, Phone, Membership_Level, Created_At
        FROM Customer WHERE Customer_ID = %s
    """, (current_user.id,))
    row = cursor.fetchone()

    cursor.execute("""
        SELECT Address_ID, Address_Line_l, Address_Line_2, City, State, Zip_Code, Country
        FROM Customer_Address WHERE Customer_ID = %s AND Deleted_At IS NULL
    """, (current_user.id,))
    addresses = cursor.fetchall()

    cursor.close()
    conn.close()

    customer = {
        "first_name": row[0],
        "last_name": row[1],
        "email": row[2],
        "phone": row[3],
        "membership_level": row[4],
        "created_at": row[5],
    }

    address_list = [
        {
            "id": a[0],
            "line1": a[1],
            "line2": a[2],
            "city": a[3],
            "state": a[4],
            "zip": a[5],
            "country": a[6]
        }
        for a in addresses
    ]

    return render_template('profile.html', customer=customer, addresses=address_list)


@user_bp.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    conn = get_db_connection()
    cursor = conn.cursor()

    first = request.form.get('first_name').strip()
    last = request.form.get('last_name').strip()
    email = request.form.get('email').strip().lower()
    phone = request.form.get('phone', '').strip()

    cursor.execute("""
        UPDATE Customer SET First_Name=%s, Last_Name=%s, Email=%s, Phone=%s,
        Updated_At=UTC_TIMESTAMP()
        WHERE Customer_ID=%s
    """, (first, last, email, phone or None, current_user.id))

    conn.commit()
    cursor.close()
    conn.close()

    flash('Profile updated successfully.')
    return redirect(url_for('user.profile'))


@user_bp.route('/profile/address/add', methods=['POST'])
@login_required
def add_address():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO Customer_Address
        (Address_Line_l, Address_Line_2, City, State, Zip_Code, Country, Customer_ID)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        request.form.get('line1').strip(),
        request.form.get('line2', '').strip() or None,
        request.form.get('city').strip(),
        request.form.get('state').strip(),
        request.form.get('zip').strip(),
        request.form.get('country').strip(),
        current_user.id
    ))

    conn.commit()
    cursor.close()
    conn.close()

    flash('Address added.')
    return redirect(url_for('user.profile'))


@user_bp.route('/profile/address/delete', methods=['POST'])
@login_required
def delete_address():
    conn = get_db_connection()
    cursor = conn.cursor()

    address_id = request.form.get('address_id')
    cursor.execute("""
        UPDATE Customer_Address SET Deleted_At=UTC_TIMESTAMP()
        WHERE Address_ID=%s AND Customer_ID=%s
    """, (address_id, current_user.id))

    conn.commit()
    cursor.close()
    conn.close()

    flash('Address removed.')
    return redirect(url_for('user.profile'))


@user_bp.route('/profile/membership/update', methods=['POST'])
@login_required
def update_membership():
    from flask import session

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT Membership_Level
        FROM Customer
        WHERE Customer_ID = %s
    """, (current_user.id,))
    row = cursor.fetchone()

    cursor.close()
    conn.close()

    current_level = row[0] if row and row[0] else "Bronze"
    selected_level = request.form.get('membership_level', 'Bronze')

    membership_prices = {
        "Bronze": 0,
        "Silver": 30,
        "Gold": 60,
        "Platinum": 100
    }

    valid_levels = list(membership_prices.keys())
    if selected_level not in valid_levels:
        selected_level = "Bronze"

    current_price = membership_prices.get(current_level, 0)
    selected_price = membership_prices.get(selected_level, 0)

    # Downgrade or same level updates immediately.
    if selected_price <= current_price:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE Customer
            SET Membership_Level = %s,
                Updated_At = UTC_TIMESTAMP()
            WHERE Customer_ID = %s
        """, (selected_level, current_user.id))

        conn.commit()
        cursor.close()
        conn.close()

        flash('Membership updated successfully.')
        return redirect(url_for('user.profile'))

    # Upgrade saves choice in session and sends user to cart.
    session["selected_membership_level"] = selected_level
    flash(f'Upgrade selected. The price difference for {selected_level} will be added at checkout.')
    return redirect(url_for('cart.cart'))


@user_bp.route('/order_history')
@login_required
def order_history():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Pull all orders for the logged-in customer, newest first.
    cursor.execute("""
        SELECT
            o.Order_ID,
            o.Order_Date,
            o.Order_Status,
            o.Fulfillment_Status,
            p.Method AS Payment_Method,
            COALESCE(SUM(oi.Amount + oi.Tax), 0) AS Order_Total,

            s.Carrier,
            s.Ship_Status,
            s.Tracking_Number,
            s.Shipped_On,
            s.Shipment_Notes

        FROM `Order` o
        LEFT JOIN Payment p
            ON o.Order_ID = p.Order_ID
        LEFT JOIN Order_Item oi
            ON o.Order_ID = oi.Order_ID
        LEFT JOIN Shipping s
            ON o.Order_ID = s.Order_ID
        WHERE o.Customer_ID = %s
        GROUP BY
            o.Order_ID,
            o.Order_Date,
            o.Order_Status,
            o.Fulfillment_Status,
            p.Method,
            s.Carrier,
            s.Ship_Status,
            s.Tracking_Number,
            s.Shipped_On,
            s.Shipment_Notes
        ORDER BY o.Order_Date DESC
    """, (current_user.id,))

    orders = cursor.fetchall()

    # Format dates and decide whether each order can be cancelled or returned.
    for order in orders:
        if order["Order_Date"]:
            order["Formatted_Order_Date"] = order["Order_Date"].strftime("%B %d, %Y at %I:%M %p")
        else:
            order["Formatted_Order_Date"] = "N/A"

        if order["Shipped_On"]:
            order["Formatted_Shipped_On"] = order["Shipped_On"].strftime("%B %d, %Y at %I:%M %p")
        else:
            order["Formatted_Shipped_On"] = "N/A"

        order_status = (order["Order_Status"] or "").lower()
        fulfillment_status = (order["Fulfillment_Status"] or "").lower()
        ship_status = (order["Ship_Status"] or "").lower()
        shipped_on = order["Shipped_On"]

        # Customer can cancel only before shipping/fulfillment starts.
        # Shipping said orders start as Paid, then move to ReadyForFulfillment/Fulfilled.
        order["Can_Cancel"] = (
            order_status in ["paid", "pending"]
            and fulfillment_status != "fulfilled"
            and ship_status not in ["shipped", "delivered", "returned"]
        )

        # Customer can request a return only after shipped/delivered,
        # within 30 days of the shipped date.
        order["Can_Return"] = False

        if (
            order_status != "cancelled"
            and ship_status in ["shipped", "delivered"]
            and shipped_on
        ):
            return_deadline = shipped_on + timedelta(days=30)
            order["Can_Return"] = datetime.now() <= return_deadline

        cursor.execute("""
            SELECT
                oi.Quantity,
                oi.Amount,
                oi.Tax,
                pr.Product_Name,
                pr.Product_Description,
                pr.Image_URL
            FROM Order_Item oi
            JOIN Inventory i
                ON oi.Inventory_ID = i.Inventory_ID
            JOIN Product pr
                ON i.Product_ID = pr.Product_ID
            WHERE oi.Order_ID = %s
        """, (order["Order_ID"],))

        items = cursor.fetchall()

        order["items"] = []
        for item in items:
            order["items"].append({
                "name": item["Product_Name"],
                "description": item["Product_Description"],
                "image": item["Image_URL"],
                "quantity": item["Quantity"],
                "line_total": float(item["Amount"] + item["Tax"])
            })

    cursor.close()
    conn.close()

    return render_template("order_history.html", orders=orders)


@user_bp.route('/order_history/cancel/<int:order_id>', methods=['POST'])
@login_required
def cancel_order(order_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT 
                o.Order_ID,
                o.Order_Status,
                o.Fulfillment_Status,
                o.Order_Date,
                s.Ship_Status,
                s.Carrier,
                s.Tracking_Number
            FROM `Order` o
            LEFT JOIN Shipping s
                ON o.Order_ID = s.Order_ID
            WHERE o.Order_ID = %s
              AND o.Customer_ID = %s
        """, (order_id, current_user.id))

        order = cursor.fetchone()

        if not order:
            flash("Order not found.")
            return redirect(url_for('user.order_history'))

        order_status = (order["Order_Status"] or "").lower()
        fulfillment_status = (order["Fulfillment_Status"] or "").lower()
        ship_status = (order["Ship_Status"] or "").lower()

        if order_status == "cancelled":
            flash("This order is already cancelled.")
            return redirect(url_for('user.order_history'))

        # Only allow cancellation before shipping begins processing the order.
        if order_status not in ["paid", "pending"]:
            flash("This order cannot be cancelled because fulfillment has already started.")
            return redirect(url_for('user.order_history'))

        if fulfillment_status == "fulfilled" or ship_status in ["shipped", "delivered", "returned"]:
            flash("This order cannot be cancelled because it has already been fulfilled or shipped.")
            return redirect(url_for('user.order_history'))

        cursor.execute("""
            UPDATE `Order`
            SET Order_Status = 'Cancelled'
            WHERE Order_ID = %s
              AND Customer_ID = %s
        """, (order_id, current_user.id))

        conn.commit()

        return redirect(url_for('user.order_cancelled', order_id=order_id))

    except Exception as err:
        conn.rollback()
        print("Cancel order error:", err)
        flash("There was an error cancelling the order.")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('user.order_history'))


@user_bp.route('/order_history/cancelled/<int:order_id>')
@login_required
def order_cancelled(order_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            o.Order_ID,
            o.Order_Date,
            o.Order_Status,
            o.Fulfillment_Status,
            s.Ship_Status,
            s.Carrier,
            s.Tracking_Number
        FROM `Order` o
        LEFT JOIN Shipping s
            ON o.Order_ID = s.Order_ID
        WHERE o.Order_ID = %s
          AND o.Customer_ID = %s
    """, (order_id, current_user.id))

    order = cursor.fetchone()

    cursor.close()
    conn.close()

    if not order:
        flash("Order not found.")
        return redirect(url_for('user.order_history'))

    if order["Order_Date"]:
        order["Formatted_Order_Date"] = order["Order_Date"].strftime("%B %d, %Y at %I:%M %p")
    else:
        order["Formatted_Order_Date"] = "N/A"

    return render_template("order_cancelled.html", order=order)


@user_bp.route('/order_history/return/<int:order_id>', methods=['POST'])
@login_required
def return_order(order_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT 
                o.Order_ID,
                o.Order_Status,
                s.Shipping_ID,
                s.Ship_Status,
                s.Shipped_On,
                s.Carrier,
                s.Tracking_Number
            FROM `Order` o
            JOIN Shipping s
                ON o.Order_ID = s.Order_ID
            WHERE o.Order_ID = %s
              AND o.Customer_ID = %s
        """, (order_id, current_user.id))

        order = cursor.fetchone()

        if not order:
            flash("Order or shipping record not found.")
            return redirect(url_for('user.order_history'))

        order_status = (order["Order_Status"] or "").lower()
        ship_status = (order["Ship_Status"] or "").lower()
        shipped_on = order["Shipped_On"]

        if order_status == "cancelled":
            flash("Cancelled orders cannot be returned.")
            return redirect(url_for('user.order_history'))

        if ship_status == "returned":
            flash("This order has already been marked as returned.")
            return redirect(url_for('user.order_history'))

        if ship_status not in ["shipped", "delivered"]:
            flash("This order cannot be returned because it has not shipped yet.")
            return redirect(url_for('user.order_history'))

        if not shipped_on:
            flash("This order cannot be returned because there is no shipped date.")
            return redirect(url_for('user.order_history'))

        return_deadline = shipped_on + timedelta(days=30)

        if datetime.now() > return_deadline:
            flash("This order is past the 30-day return window.")
            return redirect(url_for('user.order_history'))

        # Create a simple return tracking/label number for the shipping team.
        # This is not a real carrier label, but it gives shipping a populated return label ID.
        return_tracking_number = ''.join(random.choices(string.ascii_uppercase + string.digits, k=18))

        cursor.execute("""
            UPDATE Shipping
            SET Ship_Status = 'Returned',
                Tracking_Number = %s,
                Status_Updated_At = UTC_TIMESTAMP(),
                Updated_At = UTC_TIMESTAMP(),
                Shipment_Notes = CONCAT(
                    COALESCE(Shipment_Notes, ''),
                    CASE 
                        WHEN Shipment_Notes IS NULL OR Shipment_Notes = '' THEN ''
                        ELSE ' | '
                    END,
                    'Return label created. Customer return requested.'
                ),
                Return_Reason = 'Customer requested return within 30-day return window.'
            WHERE Shipping_ID = %s
        """, (
            return_tracking_number,
            order["Shipping_ID"]
        ))

        conn.commit()

        return redirect(url_for('user.order_returned', order_id=order_id))

    except Exception as err:
        conn.rollback()
        print("Return order error:", err)
        flash("There was an error requesting the return.")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('user.order_history'))


@user_bp.route('/order_history/returned/<int:order_id>')
@login_required
def order_returned(order_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            o.Order_ID,
            o.Order_Date,
            o.Order_Status,
            o.Fulfillment_Status,
            s.Ship_Status,
            s.Carrier,
            s.Tracking_Number,
            s.Shipped_On,
            s.Shipment_Notes
        FROM `Order` o
        JOIN Shipping s
            ON o.Order_ID = s.Order_ID
        WHERE o.Order_ID = %s
          AND o.Customer_ID = %s
    """, (order_id, current_user.id))

    order = cursor.fetchone()

    cursor.close()
    conn.close()

    if not order:
        flash("Order not found.")
        return redirect(url_for('user.order_history'))

    if order["Order_Date"]:
        order["Formatted_Order_Date"] = order["Order_Date"].strftime("%B %d, %Y at %I:%M %p")
    else:
        order["Formatted_Order_Date"] = "N/A"

    if order["Shipped_On"]:
        order["Formatted_Shipped_On"] = order["Shipped_On"].strftime("%B %d, %Y at %I:%M %p")
    else:
        order["Formatted_Shipped_On"] = "N/A"

    return render_template("order_returned.html", order=order)