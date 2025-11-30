from flask import Flask, render_template, request, redirect, url_for, session, jsonify, make_response
from pymongo import MongoClient
from functools import wraps
import urllib.parse
from bson import ObjectId
from datetime import datetime, timedelta
import io
import csv
from collections import Counter, defaultdict
import statistics
from flask import make_response
import re
import os



app = Flask(__name__)
app.secret_key = "supersecretkey"

# --- MongoDB Connection ---
username = urllib.parse.quote_plus("ramagirisaiganesh5103")
password = urllib.parse.quote_plus("Rganesh@5103")
client = MongoClient(f"mongodb+srv://{username}:{password}@cluster0.crbnvgr.mongodb.net/")
db = client["finance_tracker"]

users_collection = db["users"]
books_collection = db["books"]
transactions_collection = db["transactions"]

print("✅ MongoDB Connected Successfully")

# --- Default Categories (EMOJI ONLY) ---
DEFAULT_CATEGORIES = [
    "🍱 Food",
    "✈️ Travel",
    "💡 Bills",
    "🛍️ Shopping",
    "💊 Health",
    "📚 Education",
    "💰 Salary",
    "🎮 Entertainment",
    "🏠 Rent",
    "🧾 Groceries",
    "📦 Other"
]

# --- Time helpers (IST) ---
IST_OFFSET = timedelta(hours=5, minutes=30)
def remove_emoji(text):
    return re.sub(r"[^\x00-\x7F]+", "", text)

def parse_user_date(d):
    """Parse YYYY-MM-DD string from user and convert to datetime (start of day)."""
    try:
        return datetime.fromisoformat(d + "T00:00:00") - IST_OFFSET
    except:
        return None

def now_ist():
    """Return current datetime in UTC-naive with IST offset applied (so storing naive datetimes)."""
    return datetime.utcnow() + IST_OFFSET

def format_dt(dt):
    """Format a datetime (or string) into IST display string. Safe to call with None."""
    if not dt:
        return ""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except Exception:
            return dt
    try:
        dt_ist = dt + IST_OFFSET
        return dt_ist.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(dt)

# --- Login Required Decorator ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# --- Insight generation (robust) ---
def generate_insights(transactions):
    """
    Given a list of transaction dicts, return a list of insight strings.
    Transactions expected keys: type (Income/Expense), amount (float), category (str), description (str), date (datetime or str)
    This function is defensive: uses .get to avoid KeyError.
    """
    insights = []
    if not transactions:
        return ["No transactions recorded yet."]

    # Normalize amounts and ensure date presence for further processing
    for t in transactions:
        try:
            t["amount"] = float(t.get("amount", 0) or 0)
        except Exception:
            t["amount"] = 0.0
        if not t.get("date"):
            t["date"] = now_ist()

    incomes = [t for t in transactions if t.get("type") == "Income"]
    expenses = [t for t in transactions if t.get("type") == "Expense"]

    total_income = sum(t["amount"] for t in incomes)
    total_expense = sum(t["amount"] for t in expenses)
    balance = total_income - total_expense

    insights.append(f"Total income: ₹{total_income:.2f} — Total expense: ₹{total_expense:.2f} — Balance: ₹{balance:.2f}")

    # Top expense categories
    expense_categories = [t.get("category", "📦 Other") for t in expenses]
    if expense_categories:
        cat_counts = Counter(expense_categories)
        top = cat_counts.most_common(3)
        top_list = ", ".join([f"{c} ({n} tx)" for c, n in top])
        insights.append(f"Top expense categories: {top_list}.")

    # Largest expense
    if expenses:
        largest = max(expenses, key=lambda x: x["amount"])
        desc = largest.get("description", "")
        cat = largest.get("category", "📦 Other")
        date_str = format_dt(largest.get("date"))
        insights.append(f"Largest single expense: ₹{largest['amount']:.2f} — {desc} in {cat} on {date_str}.")

    # Average expense
    expense_vals = [t["amount"] for t in expenses]
    if expense_vals:
        avg = statistics.mean(expense_vals)
        insights.append(f"Average expense per transaction: ₹{avg:.2f}.")

    # Recurring expense categories (>=3 occurrences)
    recurring = [cat for cat, cnt in Counter(expense_categories).items() if cnt >= 3]
    if recurring:
        insights.append(f"Recurring expense categories detected: {', '.join(recurring)} — review subscriptions/regular bills.")

    # Simple month-over-month trend for expenses (last 6 months)
    by_month = defaultdict(float)
    for t in expenses:
        d = t.get("date")
        if isinstance(d, str):
            try:
                d = datetime.fromisoformat(d)
            except Exception:
                continue
        month = (d + IST_OFFSET).strftime("%Y-%m")
        by_month[month] += t["amount"]
    months_sorted = sorted(by_month.items())
    if len(months_sorted) >= 2:
        last_month, last_val = months_sorted[-1]
        prev_month, prev_val = months_sorted[-2]
        if prev_val > 0:
            pct = (last_val - prev_val) / prev_val * 100
            if pct > 20:
                insights.append(f"Spending jumped by {pct:.0f}% in {last_month} vs {prev_month}.")
            elif pct < -20:
                insights.append(f"Spending dropped by {abs(pct):.0f}% in {last_month} vs {prev_month}.")
        else:
            if last_val > 0:
                insights.append(f"Spending appeared in {last_month} (no spending recorded in {prev_month}).")

    # Savings / budget tip
    if balance > 0:
        insights.append("You're positive — consider automating a percentage of income to savings.")
    else:
        insights.append("Expenses exceed income — consider trimming top categories or setting a budget.")

    # Return a compact set (limit to 8)
    return insights[:8]



@app.route("/download_pdf/<book_name>")
@login_required
def download_pdf(book_name):
    username = session["username"]

    transactions = list(transactions_collection.find({
        "username": username,
        "book_name": book_name
    }))

    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # Title
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"Transaction Report: {book_name}", ln=True, align='C')
    pdf.ln(5)

    # Table Headers
    pdf.set_font("Arial", "B", 12)
    pdf.cell(35, 8, "Type", border=1)
    pdf.cell(65, 8, "Description", border=1)
    pdf.cell(30, 8, "Amount", border=1)
    pdf.cell(45, 8, "Category", border=1)
    pdf.ln()

    # Table Rows
    pdf.set_font("Arial", size=11)
    for t in transactions:
        desc = str(t.get("description", ""))[:30].encode("latin-1", "ignore").decode("latin-1")
        cat = str(t.get("category", "")).encode("latin-1", "ignore").decode("latin-1")

        pdf.cell(35, 8, t.get("type", ""), border=1)
        pdf.cell(65, 8, desc, border=1)
        pdf.cell(30, 8, str(t.get("amount", "")), border=1)
        pdf.cell(45, 8, cat, border=1)
        pdf.ln()

    pdf_filename = f"{book_name}_transactions.pdf"

    # FIXED ↓↓↓ (returns proper bytes)
    pdf_bytes = bytes(pdf.output(dest="S"))

    return pdf_bytes, {
        "Content-Type": "application/pdf",
        "Content-Disposition": f"attachment; filename={pdf_filename}"
    }




# ---------------- ROUTES ---------------- #

@app.route("/")
@login_required
def index():
    username = session["username"]
    books = [b["book_name"] for b in books_collection.find({"username": username})]
    return render_template("dashboard.html", books=books, username=username)

@app.route("/create_book", methods=["POST"])
@login_required
def create_book():
    username = session["username"]
    book_name = request.form["book_name"].strip()
    if not book_name:
        return redirect(url_for("index"))

    existing = books_collection.find_one({"username": username, "book_name": book_name})
    if not existing:
        books_collection.insert_one({
            "username": username,
            "book_name": book_name,
            # store an initial categories array to allow user categories later
            "categories": DEFAULT_CATEGORIES.copy()
        })
        print(f"[DEBUG] Created new book '{book_name}' for user '{username}'")
    return redirect(url_for("open_book", book_name=book_name))

@app.route("/book/<book_name>")
@login_required
def open_book(book_name):
    username = session["username"]

    # Ensure book belongs to this user
    book = books_collection.find_one({"username": username, "book_name": book_name})
    if not book:
        return "❌ You don't have access to this book."

    # Merge default emoji categories with book's categories (preserve user-added too)
    existing_categories = book.get("categories", [])
    # Ensure defaults present, preserve user categories, maintain order: defaults first, then user extras
    merged = DEFAULT_CATEGORIES.copy()
    for c in existing_categories:
        if c not in merged:
            merged.append(c)

    categories = merged

    # Load transactions
    transactions = list(transactions_collection.find({"username": username, "book_name": book_name}))
    for t in transactions:
        # ensure _id is string for templates
        t["_id"] = str(t.get("_id"))
        # ensure amount numeric
        try:
            t["amount"] = float(t.get("amount", 0) or 0)
        except Exception:
            t["amount"] = 0.0
        # ensure category present
        if "category" not in t or not t.get("category"):
            t["category"] = "📦 Other"
        # ensure date present and produce date_str for template display
        if not t.get("date"):
            t["date"] = now_ist()
        t["date_str"] = format_dt(t.get("date"))

    income = sum(t["amount"] for t in transactions if t.get("type") == "Income")
    expense = sum(t["amount"] for t in transactions if t.get("type") == "Expense")
    total = income - expense

    # insights using the robust generator
    insights = generate_insights(transactions)

    return render_template(
        "book.html",
        book_name=book_name,
        expenses=transactions,
        income=income,
        expense=expense,
        total=total,
        insights=insights,
        categories=categories
    )

@app.route("/add_entry/<book_name>", methods=["POST"])
@login_required
def add_entry(book_name):
    username = session["username"]
    entry_type = request.form.get("type", "Expense")
    description = request.form.get("description", "").strip()
    try:
        amount = float(request.form.get("amount", 0) or 0)
    except Exception:
        amount = 0.0

    # Category: allow user to pick a predefined OR enter a custom category
    category = request.form.get("category", "")
    custom_category = request.form.get("custom_category", "").strip()
    if category == "__custom__" or (not category and custom_category):
        # use exactly what the user typed, preserve spelling & emojis
        if custom_category:
            category = custom_category
            # Persist custom category to book's categories (addToSet-like behavior)
            books_collection.update_one(
                {"book_name": book_name, "username": username},
                {"$addToSet": {"categories": custom_category}}
            )
        else:
            category = "📦 Other"
    elif not category:
        category = "📦 Other"

    # Date handling: accept a date (YYYY-MM-DD or ISO) or use now_ist
    date_str = request.form.get("date", "").strip()
    if date_str:
        try:
            if "T" in date_str:
                dt = datetime.fromisoformat(date_str)
            else:
                dt = datetime.fromisoformat(date_str + "T00:00:00")
        except Exception:
            dt = now_ist()
    else:
        dt = now_ist()

    transactions_collection.insert_one({
        "username": username,
        "book_name": book_name,
        "type": entry_type,
        "description": description,
        "amount": amount,
        "category": category,
        "date": dt
    })

    print(f"[DEBUG] Added entry {entry_type} ₹{amount} ({category}) at {dt}")
    return redirect(url_for("open_book", book_name=book_name))

@app.route("/delete_entry/<book_name>/<entry_id>", methods=["POST"])
@login_required
def delete_entry(book_name, entry_id):
    username = session["username"]
    try:
        obj_id = ObjectId(entry_id)
    except Exception:
        return jsonify({"status": "error", "message": "Invalid ID"}), 400

    result = transactions_collection.delete_one({
        "_id": obj_id,
        "username": username,
        "book_name": book_name
    })
    if result.deleted_count == 1:
        # quick successful response — frontend can remove the row without full reload
        return jsonify({"status": "success"}), 200
    else:
        return jsonify({"status": "error", "message": "Not found"}), 404

@app.route("/edit_entry/<book_name>/<entry_id>", methods=["POST"])
@login_required
def edit_entry(book_name, entry_id):
    username = session["username"]
    data = request.get_json() or {}

    description = data.get("description", "").strip()
    try:
        amount = float(data.get("amount", 0) or 0)
    except Exception:
        amount = 0.0
    entry_type = data.get("type", "Expense")
    category = data.get("category", "").strip()
    date_str = data.get("date", "").strip() if data.get("date") else ""

    # handle category: if custom, accept and persist
    if category == "__custom__" or (category and category not in DEFAULT_CATEGORIES):
        # if user provided a custom name in payload, it's expected they also sent it as `category`
        # persist it
        books_collection.update_one(
            {"book_name": book_name, "username": username},
            {"$addToSet": {"categories": category}}
        )
    if not category:
        category = "📦 Other"

    # parse date if provided; otherwise don't overwrite existing date
    dt = None
    if date_str:
        try:
            dt = datetime.fromisoformat(date_str) if "T" in date_str else datetime.fromisoformat(date_str + "T00:00:00")
        except Exception:
            dt = now_ist()

    update_fields = {
        "description": description,
        "amount": amount,
        "type": entry_type,
        "category": category
    }
    if dt is not None:
        update_fields["date"] = dt

    transactions_collection.update_one(
        {"_id": ObjectId(entry_id), "username": username, "book_name": book_name},
        {"$set": update_fields}
    )
    return jsonify({"status": "success"})

@app.route("/ai_insights/<book_name>")
@login_required
def ai_insights(book_name):
    username = session["username"]
    transactions = list(transactions_collection.find({"username": username, "book_name": book_name}))
    # defensive normalization
    for t in transactions:
        try:
            t["amount"] = float(t.get("amount", 0) or 0)
        except Exception:
            t["amount"] = 0.0
        if "date" not in t or not t.get("date"):
            t["date"] = now_ist()
    insights = generate_insights(transactions)
    return jsonify({"status": "success", "insights": insights})

@app.route("/download_csv/<book_name>")
@login_required
def download_csv(book_name):
    username = session["username"]
    transactions = list(transactions_collection.find({"username": username, "book_name": book_name}))
    csv_content, filename = transactions_to_csv(transactions, book_name)
    response = make_response(csv_content)
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    return response

# --- Auth routes (unchanged) ---
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        password = request.form["password"].strip()
        if users_collection.find_one({"username": username}):
            return "⚠️ Username already exists!"
        users_collection.insert_one({"username": username, "password": password})
        return redirect(url_for("login"))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        password = request.form["password"].strip()
        user = users_collection.find_one({"username": username})
        if not user or user["password"] != password:
            return "❌ Invalid credentials!"
        session["username"] = username
        return redirect(url_for("index"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect(url_for("login"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
