import tkinter as tk
from tkinter import ttk
from database import cursor

# Get all the stuff needed for payment processing

def get_payments():
    query = """
        SELECT Payment_ID, 
                Order_ID, 
                Method, 
                Payment_Status
        FROM Payment;
    """

    cursor.execute(query)
    results = cursor.fetchall()
    return results

# UI Data

def display_payments(payments):
    print("\n--- Payment Records ---")
    for payment in payments:
        payment_id, order_id, method, status = payment

        print(f"Payment ID:     {payment_id}")
        print(f"Order ID:       {order_id}")
        print(f"Method:         {method}")
        print(f"Payment Status: {status}")
        print("------------------------")

# UI

def payment_ui(payments):
    window = tk.Tk()
    window.title("Payment Records")
    window.geometry("900x600")

    # table
    columns = ("Payment_ID", "Order_ID", "Method", "Status")
    tree = ttk.Treeview(window, columns=columns, show="headings")

    # headings
    tree.heading("Payment_ID", text="Payment ID")
    tree.heading("Order_ID", text="Order ID")
    tree.heading("Method", text="Method")
    tree.heading("Status", text="Status")

    # rows
    for payment in payments:
        tree.insert("", tk.END, values=payment)

    tree.pack(expand=True, fill="both")
    window.mainloop()

# Display

payments = get_payments()
payment_ui(payments)
