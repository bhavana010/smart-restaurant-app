import os
import pyodbc
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import (
    LoginManager, login_user, login_required,
    logout_user, current_user, UserMixin
)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv


# ============================================================
#  LOAD ENVIRONMENT
# ============================================================
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# ------------------------------------------------------------
#  DATABASE CONNECTION
# ------------------------------------------------------------
CONN_STR = os.getenv("SQL_SERVER_CONN_STR")

def get_conn():
    return pyodbc.connect(CONN_STR)


# ============================================================
#  FLASK-LOGIN SETUP
# ============================================================
login_manager = LoginManager(app)
login_manager.login_view = "login"   # IMPORTANT (Fixes your error)

class User(UserMixin):
    def __init__(self, id, username, email, role):
        self.id = id
        self.username = username
        self.email = email
        self.role = role


@login_manager.user_loader
def load_user(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT UserID, Username, Email, Role FROM Users WHERE UserID = ?", user_id)
    row = cur.fetchone()
    conn.close()

    if row:
        return User(row.UserID, row.Username, row.Email, row.Role)
    return None


# ============================================================
#  HOME PAGE
# ============================================================
@app.route("/")
@login_required
def index():
    return render_template("base.html")


# ============================================================
#  REGISTER
# ============================================================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        role = "Customer"

        password_hash = generate_password_hash(password)

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO Users (Username, Email, PasswordHash, Role) VALUES (?, ?, ?, ?)",
            (username, email, password_hash, role),
        )
        conn.commit()
        conn.close()

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


# ============================================================
#  LOGIN
# ============================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT UserID, Username, Email, PasswordHash, Role FROM Users WHERE Email = ?", email)
        row = cur.fetchone()
        conn.close()

        if row and check_password_hash(row.PasswordHash, password):
            user = User(row.UserID, row.Username, row.Email, row.Role)
            login_user(user)
            flash("Logged in successfully!", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid email or password", "danger")

    return render_template("login.html")


# ============================================================
#  LOGOUT
# ============================================================
@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ============================================================
#  MENU LIST (READ)
# ============================================================
@app.route("/menu")
@login_required
def menu_list():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT m.MenuItemID, m.Name, c.Name AS CategoryName, m.Price, m.Active
        FROM MenuItems m
        JOIN Categories c ON m.CategoryID = c.CategoryID
        ORDER BY m.Name
    """)
    items = cur.fetchall()
    conn.close()

    return render_template("menu_list.html", items=items)


# ============================================================
#  MENU CREATE (CREATE)
# ============================================================
@app.route("/menu/create", methods=["GET", "POST"])
@login_required
def menu_create():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT CategoryID, Name FROM Categories")
    categories = cur.fetchall()

    if request.method == "POST":
        name = request.form["name"]
        category_id = request.form["category_id"]
        price = request.form["price"]
        active = 1 if "active" in request.form else 0

        cur.execute(
            "INSERT INTO MenuItems (Name, CategoryID, Price, Active) VALUES (?, ?, ?, ?)",
            (name, category_id, price, active)
        )
        conn.commit()
        conn.close()

        flash("Menu item created successfully!", "success")
        return redirect(url_for("menu_list"))

    conn.close()
    return render_template("menu_form.html", categories=categories, item=None)


# ============================================================
#  ANALYTICS (Chart.js)
# ============================================================
@app.route("/analytics")
@login_required
def analytics():
    conn = get_conn()
    cur = conn.cursor()

    # Revenue per day
    cur.execute("""
        SELECT CAST(OrderTime AS DATE) AS OrderDate,
               SUM(TotalAmount) AS TotalRevenue
        FROM Orders
        GROUP BY CAST(OrderTime AS DATE)
        ORDER BY OrderDate
    """)
    revenue_rows = cur.fetchall()

    dates = [str(r.OrderDate) for r in revenue_rows]
    revenues = [float(r.TotalRevenue) for r in revenue_rows]

    # Top 5 Items
    cur.execute("""
        SELECT TOP 5 mi.Name, SUM(od.Quantity * od.UnitPrice) AS TotalRevenue
        FROM OrderDetails od
        JOIN MenuItems mi ON od.MenuItemID = mi.MenuItemID
        GROUP BY mi.Name
        ORDER BY TotalRevenue DESC
    """)
    top_rows = cur.fetchall()

    item_names = [r.Name for r in top_rows]
    item_revenues = [float(r.TotalRevenue) for r in top_rows]

    conn.close()

    return render_template(
        "analytics.html",
        dates=dates,
        revenues=revenues,
        item_names=item_names,
        item_revenues=item_revenues
    )
# ============================================================
#  MENU EDIT (UPDATE)
# ============================================================
@app.route("/menu/edit/<int:id>", methods=["GET", "POST"])
@login_required
def menu_edit(id):
    conn = get_conn()
    cur = conn.cursor()

    # Get item
    cur.execute("SELECT * FROM MenuItems WHERE MenuItemID = ?", (id,))
    item = cur.fetchone()

    # Get categories
    cur.execute("SELECT CategoryID, Name FROM Categories")
    categories = cur.fetchall()

    if request.method == "POST":
        name = request.form["name"]
        category_id = request.form["category_id"]
        price = request.form["price"]
        active = 1 if request.form.get("active") else 0

        cur.execute("""
            UPDATE MenuItems
            SET Name = ?, CategoryID = ?, Price = ?, Active = ?
            WHERE MenuItemID = ?
        """, (name, category_id, price, active, id))

        conn.commit()
        conn.close()

        flash("Menu item updated successfully!", "success")
        return redirect(url_for("menu_list"))

    conn.close()
    return render_template("menu_form.html", item=item, categories=categories)
# ============================================================
#  MENU DELETE
# ============================================================
@app.route("/menu/delete/<int:id>")
@login_required
def menu_delete(id):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("DELETE FROM MenuItems WHERE MenuItemID = ?", (id,))
    conn.commit()
    conn.close()

    flash("Menu item deleted.", "info")
    return redirect(url_for("menu_list"))





# ============================================================
#  START APP
# ============================================================
if __name__ == "__main__":
    app.run(debug=True)
