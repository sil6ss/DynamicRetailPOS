import tkinter
from tkinter import *
from tkinter import ttk
from PIL import Image, ImageTk
from datetime import datetime
import requests
from io import BytesIO
import threading
from database import cursor

def getProducts():
        cursor.execute(""" SELECT Product.Product_Name, Product.Product_Description, Product_Category.Category_Name, Inventory.Quantity, Inventory.Unit_Price, Product.Image_URL
        FROM Product
        INNER JOIN Inventory
        ON Product.Product_ID = Inventory.Product_ID
        INNER JOIN Product_Category
        ON Product.Category_ID = Product_Category.Category_ID 
        """)
        return cursor.fetchall()
IMG_WIDTH = 120
IMG_HEIGHT = 90

def load_Image_async(url, label, size=(IMG_WIDTH,IMG_HEIGHT)):
    def fetch():
        try:
            response = requests.get(url, timeout=5)
            img = Image.open(BytesIO(response.content)).resize(size)
            photo = ImageTk.PhotoImage(img)

            label.after(0, lambda: update_label(label, photo))
        except Exception as e:
            print(f"Failed to load image: {e}")
            return None
    threading.Thread(target=fetch, daemon=True).start()

def update_label(label, photo):
    try:
        if label.winfo_exists():
            label.config(image=photo)
            label.image = photo
    except tkinter.TclError:
        pass

def create_product_grid(parent, products):
    for widget in parent.winfo_children():
        widget.destroy()

    if not products:
        ttk.Label(parent, text="No products found", font=("Arial", 12)).grid(row=0,column=0, pady=20)
        return

    COLUMNS = 3

    for i, products in enumerate(products):
        row = i // COLUMNS
        col = i % COLUMNS

        card = ttk.Frame(parent, borderwidth=2, relief="groove", padding=10)
        card.grid(row=row, column=col,padx=10,pady=10)



        img_label = tkinter.Label(card, bg="lightgray", width=15, height=7)


        img_label.pack()

        img_label.config(width=IMG_WIDTH, height=IMG_HEIGHT)
        img_label.pack_propagate(False)

        load_Image_async(products[5], img_label)

        name_label = tkinter.Label(card, text=products[0], font=("Arial", 11, "bold"))
        name_label.pack(pady=(8,2))

        price_label = tkinter.Label(card, text=f"${products[4]:.2f}", foreground="green")
        price_label.pack()
def filter_products(query, all_products):
    query= query.lower().strip()
    if not query:
        return all_products
    results = []
    for products in all_products:
        name = str(products[0]).lower()
        category = str(products[2]).lower()
        if query in name or query in category:
            results.append(products)

    return results

def setup_ui(root, all_products):
    search_frame = ttk.Frame(root, padding=10)
    search_frame.pack(fill="x")

    ttk.Label(search_frame, text="Search:").pack(side="left", padx=(0,5))

    search_var = tkinter.StringVar()
    search_entry= ttk.Entry(search_frame, textvariable=search_var,width=40)
    search_entry.pack(side="left")
    search_entry.focus()

    clear = ttk.Button(search_frame, text="X", width=3, command=lambda: search_var.set(""))
    clear.pack(side="left",padx=5)

    canvas = tkinter.Canvas(root)
    scrollbar = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
    scroll_frame = ttk.Frame(canvas)

    scroll_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

    def on_search(*args):
        query = search_var.get()
        filtered = filter_products(query, all_products)
        canvas.yview_moveto(0)
        create_product_grid(scroll_frame, filtered)

    search_var.trace_add("write", on_search)

    create_product_grid(scroll_frame, all_products)

root = Tk()
root.title=("Retail POS")
root.geometry("800x600")

inventory = getProducts()

setup_ui(root, inventory)

root.mainloop()