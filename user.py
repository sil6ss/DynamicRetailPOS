from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user

user_bp = Blueprint('user', __name__)
user_bp.secret_key = "elevate-retail-secret-key"


@user_bp.route('/profile')
@login_required
def profile():
    from home import conn
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

    customer = {
        "first_name": row[0], "last_name": row[1],
        "email": row[2], "phone": row[3],
        "membership_level": row[4], "created_at": row[5],
    }
    address_list = [
        {"id": a[0], "line1": a[1], "line2": a[2],
         "city": a[3], "state": a[4], "zip": a[5], "country": a[6]}
        for a in addresses
    ]

    return render_template('profile.html', customer=customer, addresses=address_list)


@user_bp.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    from home import conn
    cursor = conn.cursor()
    first = request.form.get('first_name').strip()
    last  = request.form.get('last_name').strip()
    email = request.form.get('email').strip().lower()
    phone = request.form.get('phone', '').strip()

    cursor.execute("""
        UPDATE Customer SET First_Name=%s, Last_Name=%s, Email=%s, Phone=%s,
        Updated_At=GETUTCDATE()
        WHERE Customer_ID=%s
    """, (first, last, email, phone or None, current_user.id))
    from home import conn
    conn.commit()
    cursor.close()
    flash('Profile updated successfully.')
    return redirect(url_for('user.profile'))

@user_bp.route('/profile/address/add', methods=['POST'])
@login_required
def add_address():
    from home import conn
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
    flash('Address added.')
    return redirect(url_for('user.profile'))

@user_bp.route('/profile/address/delete', methods=['POST'])
@login_required
def delete_address():
    from home import conn
    cursor = conn.cursor()
    address_id = request.form.get('address_id')
    cursor.execute("""
        UPDATE Customer_Address SET Deleted_At=GETUTCDATE()
        WHERE Address_ID=%s AND Customer_ID=%s
    """, (address_id, current_user.id))
    conn.commit()
    cursor.close()
    flash('Address removed.')
    return redirect(url_for('user.profile'))