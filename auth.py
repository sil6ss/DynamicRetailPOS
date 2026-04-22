from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, UserMixin

auth_bp = Blueprint('auth', __name__)
auth_bp.secret_key = "elevate-retail-secret-key"

class User(UserMixin):
    def __init__(self, customer_id, first_name, last_name, email):
        self.id = customer_id
        self.first_name = first_name
        self.last_name = last_name
        self.email = email

def get_cursor():
    from home import conn
    conn.ping(reconnect=True)  # reconnects if the connection dropped
    return conn.cursor()

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        cursor = get_cursor()
        email      = request.form.get('email').strip().lower()
        first_name = request.form.get('first_name').strip().lower()

        cursor.execute("""
            SELECT Customer_ID, First_Name, Last_Name, Email
            FROM Customer
            WHERE LOWER(Email) = %s AND LOWER(First_Name) = %s
            AND Deleted_At IS NULL
        """, (email, first_name))
        row = cursor.fetchone()
        cursor.close()

        if not row:
            flash('No account found with that email and first name.')
            return redirect(url_for('auth.login'))

        login_user(User(row[0], row[1], row[2], row[3]))
        return redirect(url_for('home_page'))

    return render_template('login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        from home import conn
        cursor = get_cursor()
        first = request.form.get('first_name').strip()
        last  = request.form.get('last_name').strip()
        email = request.form.get('email').strip().lower()
        phone = request.form.get('phone', '').strip()

        cursor.execute("SELECT Customer_ID FROM Customer WHERE LOWER(Email) = %s", (email,))
        if cursor.fetchone():
            cursor.close()
            flash('An account with that email already exists. Try signing in.')
            return redirect(url_for('auth.register'))

        cursor.execute("""
            INSERT INTO Customer (First_Name, Last_Name, Email, Phone, Membership_Level)
            VALUES (%s, %s, %s, %s, 'Bronze')
        """, (first, last, email, phone or None))
        conn.commit()
        cursor.close()

        flash('Account created! You can now sign in.')
        return redirect(url_for('auth.login'))

    return render_template('register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))