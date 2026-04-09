from flask import Flask, render_template, request, redirect, url_for, session, Blueprint

cart_bp = Blueprint("cart", __name__)
cart_bp.secret_key = "elevate-retail-secret-key"


# home route (sends straight to cart page right now)

# cart page route
@cart_bp.route("/cart")
def cart():
    if "cart" not in session:  # temp data
        session["cart"] = []

    cart_items = session.get("cart", [])  # gets cart items
    subtotal = sum(item["price"] * item["quantity"] for item in cart_items)  # subtotal

    tax_rate = 0.07  # sales tax
    sales_tax = subtotal * tax_rate

    shipping = 0.00  # temp shipping (waiting for infor from shipping team on prices)
    total = subtotal + sales_tax + shipping  # final total

    # cart data sent to HTML template
    return render_template(
        "cart.html",
        cart=cart_items,
        subtotal=subtotal,
        sales_tax=sales_tax,
        shipping=shipping,
        total=total
    )


# route to item quantity update
@cart_bp.route("/update_cart", methods=["POST"])
def update_cart():
    product_name = request.form["product_name"]
    quantity = int(request.form["quantity"])

    cart_items = session.get("cart", [])  # gets current cart

    # finds matching item and updates
    for item in cart_items:
        if item["name"] == product_name:
            if quantity > 0:
                item["quantity"] = quantity
            else:
                cart_items.remove(item)
            break

    session["cart"] = cart_items  # saves updated cart
    return redirect(url_for("cart.cart"))  # back to cart page


# route for completely removing item
@cart_bp.route("/remove_from_cart", methods=["POST"])
def remove_from_cart():
    product_name = request.form["product_name"]  # get product
    cart_items = session.get("cart", [])  # current cart

    cart_items = [item for item in cart_items if item["name"] != product_name]  # keeps all but removed

    # save and return
    session["cart"] = cart_items
    return redirect(url_for("cart.cart"))


# route to clear cart and reload
@cart_bp.route("/clear_cart")
def clear_cart():
    session.pop("cart", None)  # removes cart session
    return redirect(url_for("cart.cart"))  # redirects back to cart page

@cart_bp.route("/payment")
def payment():
    cart_items = session.get("cart", [])

    subtotal = sum(item["price"] * item["quantity"] for item in cart_items)
    tax_rate = 0.07
    sales_tax = subtotal * tax_rate
    shipping = 0.00
    total = subtotal + sales_tax + shipping

    return render_template(
        "payment.html",
        cart=cart_items,
        subtotal=subtotal,
        sales_tax=sales_tax,
        shipping=shipping,
        total=total
    )

@cart_bp.route("/order_confirmation")
def order_confirmation():
    payment_method = request.args.get("payment_method", "N/A")
    cart_items = session.get("cart", [])

    subtotal = sum(item["price"] * item["quantity"] for item in cart_items)
    discount = 0.00
    tax = subtotal * 0.07
    total_paid = subtotal - discount + tax

    order = {
        "order_number": "ER123456",
        "date": "April 2, 2026",
        "customer_name": "Test Customer",
        "payment_method": payment_method,
        "subtotal": subtotal,
        "discount": discount,
        "tax": tax,
        "total_paid": total_paid
    }

    order_items = []
    for item in cart_items:
        order_items.append({
            "image_url": item["image"],
            "product_name": item["name"],
            "description": item["description"],
            "quantity": item["quantity"],
            "line_total": item["price"] * item["quantity"]
        })

    return render_template(
        "order_confirmation.html",
        order=order,
        order_items=order_items
    )
