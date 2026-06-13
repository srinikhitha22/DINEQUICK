from flask import Flask, jsonify, redirect, url_for, request, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import functools
from sqlalchemy import text

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dinequick_ultimate_cancel.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'hackathon_secret_key_2026'

db = SQLAlchemy(app)

# ==============================================================================
# 📊 IN-MEMORY APP STATE LABELS
# ==============================================================================
LIVE_NOTIFICATIONS = []
NOTIFICATION_COUNTER = 0

# Master administrative and worker passcode variables stored contextually
ADMIN_CREDENTIALS = {"username": "admin", "password": "admin123"}
WORKER_CREDENTIALS = {"passcode": "workers123"}

# Secret Hackathon verification answers for resetting lost keys
SECRET_RECOVERY_TOKEN = "DINEQUICK2026"

# ==============================================================================
# 🎨 SHARED UI MODERN LIGHT MODE STYLESHEET
# ==============================================================================
GLOBAL_STYLE = """
<style>
    body { 
        background-color: #f8f9fa; 
        min-height: 100vh; 
        font-family: 'Segoe UI', system-ui, sans-serif; 
        color: #212529;
    }
    .navbar {
        background-color: #212529 !important;
        border-bottom: 2px solid #ffa502;
    }
    .clean-light-card {
        background-color: #ffffff !important;
        border: 1px solid #dee2e6 !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05) !important;
    }
    .list-group-item {
        background-color: #ffffff !important;
        color: #212529 !important;
        border-color: #dee2e6 !important;
    }
    .list-group-item:hover {
        background-color: #f1f3f5 !important;
        color: #d35400 !important;
    }
</style>
"""

# ==============================================================================
# 🛠️ DATABASE SCHEMA MODELS
# ==============================================================================
class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)

class RestaurantTable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(20), default='Vacant') 

class UserAccount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)

class CustomerOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer, nullable=False) 
    username = db.Column(db.String(80), nullable=True) 
    items_json = db.Column(db.Text, nullable=False) 
    subtotal = db.Column(db.Float, default=0.0)
    cgst = db.Column(db.Float, default=0.0)
    sgst = db.Column(db.Float, default=0.0)
    total_bill = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(30), default='Placed') 
    order_type = db.Column(db.String(20), default='Dine-In') 

# ==============================================================================
# 🔐 ROLE PROTECTION SECURITY DECORATORS
# ==============================================================================
def admin_login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def worker_login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('worker_logged_in') and not session.get('admin_logged_in'):
            return redirect(url_for('worker_login'))
        return f(*args, **kwargs)
    return decorated_function

def get_navbar(current_table=1):
    active_count = CustomerOrder.query.filter(CustomerOrder.status.in_(['Placed', 'Cooking', 'Served'])).count()
    
    if session.get('admin_logged_in'):
        admin_auth_html = '<a class="nav-link text-danger fw-bold px-2" href="/admin/logout">🔒 Admin (Logout)</a>'
        admin_panel_link = '<a class="nav-link text-info fw-semibold px-2" href="/admin-panel">🛠️ Admin Panel</a>'
    else:
        admin_auth_html = ''
        admin_panel_link = '<a class="nav-link text-info fw-semibold px-2" href="/admin-login">🔒 Admin Login</a>'

    if session.get('worker_logged_in'):
        worker_auth_html = '<a class="nav-link text-danger fw-bold px-2" href="/kitchen/logout">👨‍🍳 Worker (Logout)</a>'
    elif session.get('admin_logged_in'):
        worker_auth_html = '<span class="nav-link text-muted px-2">👁️ Admin View Mode</span>'
    else:
        worker_auth_html = '<a class="nav-link text-white fw-semibold px-2" href="/kitchen-login">👨‍🍳 Worker Login</a>'

    if session.get('user_logged_in'):
        user_auth_html = f'<a class="nav-link text-success fw-bold px-2" href="/user/logout/{current_table}">👤 {session.get("username")} (Logout)</a>'
    else:
        user_auth_html = f'<a class="nav-link text-warning fw-bold px-2" href="/user/login/{current_table}">🔑 Customer Login</a>'

    table_context_text = f"Takeaway Context" if current_table == 0 else f"Table Context: #{current_table}"

    return f"""
    <nav class="navbar navbar-expand navbar-dark mb-4 shadow">
        <div class="container-fluid">
            <a class="navbar-brand fw-bold text-warning" href="/">DineQuick ⚡</a>
            <div class="navbar-nav me-auto">
                <a class="nav-link text-white fw-semibold px-2" href="/admin">🗺️ Simulator Hub</a>
                <a class="nav-link text-white fw-semibold px-2" href="/table/{current_table}">📱 Customer Menu</a>
                <a class="nav-link text-white fw-semibold px-2" href="/kitchen">🍳 Workers Panel ({active_count} Live)</a>
                {admin_panel_link}
                {admin_auth_html}
                {worker_auth_html}
                {user_auth_html}
            </div>
            <span class="badge bg-warning text-dark fw-bold px-3 py-2 fs-6">{table_context_text}</span>
        </div>
    </nav>
    """

def get_live_alerts_html():
    """Generates light mode interactive verification cards with asynchronous staff approval hooks."""
    global LIVE_NOTIFICATIONS
    if not session.get('admin_logged_in') and not session.get('worker_logged_in'):
        return ""
        
    alerts_html = ""
    for note in LIVE_NOTIFICATIONS:
        alerts_html += f"""
        <div id="alert-node-{note['id']}" class="alert alert-warning shadow-sm border-start border-warning border-4 text-dark bg-white mb-3 p-3 d-flex justify-content-between align-items-center" role="alert">
            <div>
                <i class="fa-solid fa-circle-exclamation text-warning me-2 fs-5"></i>
                <strong>Payment Verification Required:</strong> {note['text']}
            </div>
            <div>
                <button class="btn btn-sm btn-success fw-bold px-3 rounded-pill me-2 shadow-sm" onclick="verifyAndVacateTableToServer({note['id']}, {note['order_id']})">
                    <i class="fa-solid fa-check me-1"></i> Verify & Vacate Table
                </button>
            </div>
        </div>
        """
        
    if alerts_html:
        alerts_html += """
        <script>
            function verifyAndVacateTableToServer(notificationId, orderId) {
                fetch('/api/verify_staff_payment/' + notificationId + '/' + orderId, { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    if(data.success) {
                        const element = document.getElementById('alert-node-' + notificationId);
                        if(element) element.remove();
                        window.location.reload();
                    }
                });
            }
        </script>
        """
    return alerts_html

# ==============================================================================
# HIDDEN API LAYER: ACCOUNT VERIFICATION ENGINE
# ==============================================================================
@app.route('/api/verify_staff_payment/<int:note_id>/<int:order_id>', methods=['POST'])
def verify_staff_payment(note_id, order_id):
    global LIVE_NOTIFICATIONS
    order = CustomerOrder.query.get(order_id)
    if order:
        order.status = 'Paid'
        if order.table_id > 0:
            table = RestaurantTable.query.get(order.table_id)
            if table:
                table.status = 'Vacant'
        db.session.commit()
        
    # Remove from active staff notification pool
    LIVE_NOTIFICATIONS = [n for n in LIVE_NOTIFICATIONS if n['id'] != note_id]
    return jsonify({"success": True})

# ==============================================================================
# SCREEN 0: WELCOME LANDING
# ==============================================================================
@app.route('/')
def welcome_page():
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Welcome to DineQuick</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        {GLOBAL_STYLE}
        <style>
            .welcome-card {{ background: #ffffff; border: 1px solid #dee2e6; border-radius: 24px; max-width: 650px; width: 100%; box-shadow: 0 10px 30px rgba(0,0,0,0.05); }}
            .feature-link-box {{ text-decoration: none; color: #212529; display: block; padding: 20px 10px; border-radius: 15px; border: 1px solid #e9ecef; background: #f8f9fa; transition: all 0.2s; }}
            .feature-link-box:hover {{ background: #e9ecef; transform: translateY(-3px); color: #d35400; }}
            .feature-icon {{ font-size: 2.5rem; color: #d35400; }}
            .btn-bold-glow {{ background: linear-gradient(135deg, #d35400, #e67e22); border: none; color: white; font-weight: 800; letter-spacing: 0.5px; box-shadow: 0 4px 15px rgba(211, 84, 0, 0.2); transition: all 0.2s; }}
            .btn-bold-glow:hover {{ transform: scale(1.02); box-shadow: 0 8px 25px rgba(211, 84, 0, 0.4); color: white; }}
        </style>
    </head>
    <body>
        <div class="container p-3 d-flex justify-content-center align-items-center" style="min-height:90vh;">
            <div class="welcome-card p-5 text-center shadow-lg">
                <div class="mb-2">
                    <span class="display-2 text-warning"><i class="fa-solid fa-qrcode"></i></span>
                </div>
                <h1 class="display-4 fw-bold mb-2 text-dark">Welcome to DineQuick</h1>
                <p class="text-muted fs-5 mb-4">In-Restaurant Contactless Ordering Platform</p>
                <hr class="my-4">
                <div class="row text-start justify-content-center g-4 mb-5">
                    <div class="col-sm-5 text-center">
                        <a href="/admin" class="feature-link-box">
                            <div class="feature-icon mb-2"><i class="fa-solid fa-chair"></i></div>
                            <h5 class="fw-bold mb-2">Select Table</h5>
                            <small class="text-muted d-block">Pick your active table from the floor map grid.</small>
                        </a>
                    </div>
                    <div class="col-sm-5 text-center">
                        <a href="/table/1" class="feature-link-box">
                            <div class="feature-icon mb-2"><i class="fa-solid fa-utensils"></i></div>
                            <h5 class="fw-bold mb-2">Select Items</h5>
                            <small class="text-muted d-block">Explore menu card filters and categories.</small>
                        </a>
                    </div>
                </div>
                <div class="d-grid gap-2 px-md-4">
                    <a href="/admin" class="btn btn-bold-glow p-3 fs-5 rounded-pill text-uppercase">Dine Quick Simulator ➔</a>
                </div>
                <p class="text-muted small mt-4 mb-0">Hackathon Prototype Pipeline Active</p>
            </div>
        </div>
    </body>
    </html>
    """

# ==============================================================================
# SCREEN 1: SIMULATOR HUB
# ==============================================================================
@app.route('/admin')
def qr_hub():
    tables = RestaurantTable.query.all()
    table_cards = ""
    for t in tables:
        color = "success" if t.status == 'Vacant' else "warning" if t.status == 'Ordering' else "danger"
        table_cards += f"""
        <div class="col-12 col-md-6 mb-3">
            <div class="card p-3 shadow-sm clean-light-card">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h5 class="fw-bold mb-0 text-dark">Table #{t.id}</h5>
                    <span class="badge bg-{color}">{t.status}</span>
                </div>
                <p class="text-muted small mb-3">Simulate layout execution updates live.</p>
                <a href="/table/{t.id}" class="btn btn-outline-dark btn-sm w-100 fw-bold py-2">Select Table</a>
            </div>
        </div>
        """

    user_portal_items = ""
    for t in tables:
        dot_color = "text-success" if t.status == 'Vacant' else "text-warning" if t.status == 'Ordering' else "text-danger"
        user_portal_items += f"""
        <a href="/table/{t.id}" class="list-group-item list-group-item-action d-flex justify-content-between align-items-center py-2 border-0 border-bottom">
            <div>
                <i class="fa-solid fa-circle {dot_color} me-2 small"></i>
                <span class="small fw-semibold text-dark">Customer View T#{t.id}</span>
            </div>
            <span class="badge bg-secondary text-white rounded-pill px-2 py-1" style="font-size:10px;">Open Menu ➔</span>
        </a>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>DineQuick | Simulator Hub</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">{GLOBAL_STYLE}</head>
    <body>
        {get_navbar(1)}
        <div class="container px-md-4">
            {get_live_alerts_html()}
            <div class="card p-4 shadow-sm border-0 mb-4 text-center clean-light-card" style="border-radius:15px;">
                <h2 class="fw-bold text-dark"><i class="fa-solid fa-gears text-danger me-2"></i>DineQuick Workspace Control</h2>
                <p class="text-muted mb-0">Select an active grid table node below or launch customer and takeaway views from side portals.</p>
            </div>
            <div class="row justify-content-center">
                <div class="col-lg-8 mb-4">
                    <div class="card shadow-sm border-0 p-3 clean-light-card h-100" style="border-radius:15px;">
                        <h6 class="fw-bold text-dark mb-3"><i class="fa-solid fa-border-all text-success me-2"></i>Interactive Dining Floor Grid</h6>
                        <div class="row g-2">{table_cards}</div>
                    </div>
                </div>
                <div class="col-lg-4 mb-4">
                    <div class="card shadow-sm border-0 p-3 clean-light-card mb-3" style="border-radius:15px;">
                        <h6 class="fw-bold text-dark mb-2"><i class="fa-solid fa-bag-shopping text-warning me-2"></i>Takeaway Parcel Hub</h6>
                        <p class="text-muted small mb-3">Simulate express off-table counter takeaway orders instantly.</p>
                        <a href="/table/0" class="btn btn-warning w-100 fw-bold py-2.5 rounded-pill shadow-sm text-dark"><i class="fa-solid fa-bolt me-1"></i> Launch Takeaway Menu</a>
                    </div>
                    
                    <div class="card shadow-sm border-0 p-3 clean-light-card" style="border-radius:15px;">
                        <h6 class="fw-bold text-dark mb-2"><i class="fa-solid fa-users text-danger me-2"></i>User Simulator Portal</h6>
                        <p class="text-muted mb-3" style="font-size:12px;">Emulate scanning the QR code patch right from the client's perspective.</p>
                        <div class="list-group list-group-flush border rounded-3 overflow-hidden shadow-sm">
                            {user_portal_items}
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            if ({ 'true' if session.get('admin_logged_in') or session.get('worker_logged_in') else 'false' }) {{
                setTimeout(() => {{ window.location.reload(); }}, 5000);
            }}
        </script>
    </body>
    </html>
    """

# ==============================================================================
# SCREEN 2: CUSTOMER FOOD MENU CARD
# ==============================================================================
@app.route('/table/<int:table_id>')
def browse_menu(table_id):
    if table_id > 0:
        table = RestaurantTable.query.get(table_id)
        if table and table.status == 'Vacant':
            table.status = 'Ordering'
            db.session.commit()

    existing_order = CustomerOrder.query.filter(CustomerOrder.table_id == table_id, CustomerOrder.status.in_(['Placed', 'Cooking', 'Served', 'Paid - Pending Verification'])).order_by(CustomerOrder.id.desc()).first()
    alert_box = ""
    if existing_order:
        if existing_order.status == 'Paid - Pending Verification':
            alert_box = f"""
            <div class="alert alert-warning shadow-sm text-center fw-bold mb-4 text-dark">
                ⏳ Payment Processing: Your transaction is currently awaiting verification from the restaurant staff. Please wait seated at Table #{table_id}.
            </div>
            """
        else:
            color = "info" if existing_order.status != 'Served' else "success"
            alert_box = f"""
            <div class="alert alert-{color} shadow-sm text-center fw-bold mb-4 text-dark">
                🔔 Active Open Bill Tab Session: Current Status: <span class="text-uppercase border-bottom">{existing_order.status}</span>
                <br><small class="text-muted">Any new items added will be automatically appended to this continuous bill.</small>
                <br><a href="/bill_generation/{existing_order.id}" class="btn btn-sm btn-dark mt-2 text-white">🧾 Check Active Combined Bill Tab</a>
            </div>
            """

    items = MenuItem.query.all()
    menu_rows = ""
    for i in items:
        menu_rows += f"""
        <div class="card p-3 mb-2 border-0 shadow-sm d-flex flex-row justify-content-between align-items-center clean-light-card">
            <div><h6 class="fw-bold mb-0 text-dark">{i.name}</h6><span class="text-success fw-bold">₹{i.price}</span></div>
            <button class="btn btn-danger btn-sm rounded-pill px-3 fw-bold" onclick="addItemToBasket('{i.id}', '{i.name}', {i.price})">+ Add</button>
        </div>
        """

    is_logged_in_js = "true" if session.get('user_logged_in') else "false"
    cart_button_html = f"""
        <button class="btn btn-warning w-100 fw-bold rounded-pill shadow-sm text-dark" onclick="dispatchOrderToServer()">🔥 Place Order To Kitchen</button>
    """ if session.get('user_logged_in') else f"""
        <div id="auth-scroll-anchor" class="alert alert-warning text-center small p-2 mb-2 text-dark fw-bold">⚠️ Introduce your name below to unlock ordering round sessions!</div>
        <a href="/user/login/{table_id}" class="btn btn-dark w-100 fw-bold rounded-pill shadow-sm text-white">🔑 Quick Identification Login</a>
    """

    panel_title = f"Takeaway Parcel Menu" if table_id == 0 else f"Table #{table_id} Digital Menu Card"

    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>Menu Card</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">{GLOBAL_STYLE}</head>
    <body>
        {get_navbar(table_id)}
        <div class="container px-md-4" style="max-width: 900px;">
            {alert_box}
            <div class="card p-4 border-0 text-white shadow mb-4" style="background: linear-gradient(135deg, #d35400, #e67e22); border-radius: 15px;">
                <h4 class="fw-bold mb-0">{panel_title}</h4>
                <p class="mb-0 opacity-75 small">Logged-in sessions can fire multiple rounds of food orders directly to cooking production.</p>
            </div>
            <div class="row">
                <div class="col-md-7"><h5 class="fw-bold text-secondary mb-3">🍛 Premium Food Portfolio</h5>{menu_rows}</div>
                <div class="col-md-5">
                    <div class="card p-3 border-0 shadow-sm sticky-top clean-light-card" style="top: 20px; border-radius:12px;">
                        <h5 class="fw-bold text-dark mb-3">Interactive Cart</h5>
                        <div id="basket-box" class="small text-muted mb-3">Your cart is empty.</div>
                        <div class="d-flex justify-content-between fw-bold border-top pt-2 mb-3"><span>Subtotal:</span><span id="subtotal-tag" class="text-success">₹0</span></div>
                        {cart_button_html}
                    </div>
                </div>
            </div>
        </div>
        <script>
            let localBasket = {{}};
            const tableId = {table_id};
            const isUserLoggedIn = {is_logged_in_js};

            function addItemToBasket(id, name, price) {{
                if (!isUserLoggedIn) {{
                    alert("⚠️ Please log in with your name first before choosing items!");
                    const anchor = document.getElementById("auth-scroll-anchor");
                    if(anchor) anchor.scrollIntoView({{ behavior: "smooth", block: "center" }});
                    return;
                }}

                if(localBasket[id]) {{ localBasket[id].qty += 1; }} else {{ localBasket[id] = {{ name: name, price: price, qty: 1 }}; }}
                renderBasketView();
            }}
            function cancelItemFromBasket(id) {{
                if(localBasket[id]) {{ localBasket[id].qty -= 1; if(localBasket[id].qty <= 0) {{ delete localBasket[id]; }} }}
                renderBasketView();
            }}
            function renderBasketView() {{
                const box = document.getElementById('basket-box');
                let total = 0; box.innerHTML = "";
                if(Object.keys(localBasket).length === 0) {{ box.innerHTML = "Your cart is empty."; document.getElementById('subtotal-tag').innerText = "₹0"; return; }}
                for(let id in localBasket) {{
                    let item = localBasket[id]; total += item.price * item.qty;
                    box.innerHTML += `
                        <div class="d-flex justify-content-between align-items-center mb-2 pb-2 border-bottom">
                            <div><span class="d-block text-dark fw-bold">${{item.name}}</span><small class="text-muted">${{item.qty}}x @ ₹${{item.price}}</small></div>
                            <div class="d-flex align-items-center gap-2"><span class="fw-bold me-1 text-dark">₹${{item.price * item.qty}}</span>
                                <button class="btn btn-outline-danger btn-sm rounded-circle py-0 px-2" style="font-size: 11px;" onclick="cancelItemFromBasket('${{id}}')">🗑️</button>
                            </div>
                        </div>`;
                }}
                document.getElementById('subtotal-tag').innerText = "₹" + total;
            }}
            function dispatchOrderToServer() {{
                if(!isUserLoggedIn) {{ return alert("Please log in with your name first!"); }}
                if(Object.keys(localBasket).length === 0) return alert("Select menu items first!");
                fetch('/api/submit_order', {{
                    method: 'POST', headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ table_id: tableId, cart_data: localBasket }})
                }}).then(res => res.json()).then(data => {{
                    if(data.success) {{ alert("🚀 Round Sent! Order injected into workers terminal."); window.location.reload(); }}
                }});
            }}
        </script>
    </body>
    </html>
    """

# ==============================================================================
# CUSTOMER LOGIN PORTAL
# ==============================================================================
@app.route('/user/login/<int:table_id>', methods=['GET', 'POST'])
def user_login(table_id):
    if request.method == 'POST':
        username = request.form.get('username')
        if username and username.strip():
            session['user_logged_in'] = True
            session['username'] = username.strip()
            return redirect(url_for('browse_menu', table_id=table_id))

    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>DineQuick | Customer Identity</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">{GLOBAL_STYLE}</head>
    <body style="min-height: 100vh; display: flex; align-items: center; justify-content: center;">
        <div class="container" style="max-width: 450px;">
            <div class="card p-4 shadow rounded-3 mx-2 border-0 clean-light-card">
                <h4 class="fw-bold text-dark text-center mb-1">👤 Customer Access</h4>
                <p class="text-muted text-center small mb-4">Enter your name to initiate instant workspace ordering operations</p>
                <form method="POST">
                    <div class="mb-4">
                        <label class="small fw-bold text-secondary mb-1">Your Full Name</label>
                        <input type="text" name="username" class="form-control form-control-lg text-center bg-white text-dark border-secondary" placeholder="e.g. John Doe" required autocomplete="off">
                    </div>
                    <button type="submit" class="btn btn-warning btn-lg w-100 fw-bold py-2.5 rounded-pill text-dark shadow-sm">Verify & Access Menu Card</button>
                </form>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/user/logout/<int:table_id>')
def user_logout(table_id):
    session.pop('user_logged_in', None)
    session.pop('username', None)
    return redirect(url_for('browse_menu', table_id=table_id))

# ==============================================================================
# ADMINISTRATIVE ACCESS GATEWAY
# ==============================================================================
@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    error = ""
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_CREDENTIALS["username"] and request.form.get('password') == ADMIN_CREDENTIALS["password"]:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_panel'))
        error = "❌ Invalid Administrative Credentials!"
    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>DineQuick | Admin Login</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">{GLOBAL_STYLE}</head>
    <body style="min-height:100vh; display:flex; align-items:center; justify-content:center;">
        <div class="card p-4 border-0 shadow-lg clean-light-card" style="max-width:380px; width:100%; border-radius:15px;">
            <h4 class="fw-bold text-center text-warning mb-3">🔒 Admin Access Panel</h4>
            {f'<div class="alert alert-danger p-2 small text-center">{error}</div>' if error else ''}
            <form method="POST">
                <div class="mb-3"><label class="small fw-bold text-dark">Username</label><input type="text" name="username" class="form-control form-control-sm bg-white text-dark border-secondary" required placeholder="admin" autocomplete="off"></div>
                <div class="mb-4"><label class="small fw-bold text-dark">Password</label><input type="password" name="password" class="form-control form-control-sm bg-white text-dark border-secondary" required placeholder="••••••••"></div>
                <button type="submit" class="btn btn-warning w-100 fw-bold py-2 rounded-pill text-dark mb-2">Verify Admin</button>
            </form>
            <div class="text-center mt-2">
                <a href="/reset-passcode/admin" class="text-decoration-none text-danger small fw-semibold">❓ Forgot Password?</a>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/admin-panel')
@admin_login_required
def admin_panel():
    items = MenuItem.query.all()
    inventory_rows = "".join([f'<tr class="align-middle"><td><b>{i.name}</b> <span class="badge bg-secondary">{i.category}</span></td><td><form action="/admin/change_price/{i.id}" method="POST" class="d-flex gap-2"><div class="input-group input-group-sm" style="max-width: 120px;"><span class="input-group-text bg-light text-dark border-secondary">₹</span><input type="number" step="0.01" name="price" value="{i.price}" class="form-control bg-white text-dark border-secondary fw-bold" required></div><button type="submit" class="btn btn-sm btn-dark">Update</button></form></td></tr>' for i in items])
    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>DineQuick Security | Admin Panel</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">{GLOBAL_STYLE}</head>
    <body>
        {get_navbar(1)}
        <div class="container py-4">
            {get_live_alerts_html()}
            <div class="d-flex justify-content-between align-items-center mb-4"><h2 class="fw-bold text-dark">🛡️ Administrative Hub</h2><a href="/admin/logout" class="btn btn-outline-danger rounded-pill px-4 fw-bold">Sign Out</a></div>
            <div class="row">
                <div class="col-md-4 mb-4">
                    <div class="card p-3 border-0 shadow-sm clean-light-card" style="border-radius:12px;">
                        <h5 class="fw-bold text-success mb-3">Add Item to Menu</h5>
                        <form action="/admin/add_item" method="POST">
                            <div class="mb-2"><label class="small fw-bold text-secondary">Item Name</label><input type="text" name="name" class="form-control bg-white text-dark border-secondary" placeholder="Garlic Bread" required autocomplete="off"></div>
                            <div class="mb-2"><label class="small fw-bold text-secondary">Price (₹)</label><input type="number" step="0.01" name="price" class="form-control bg-white text-dark border-secondary" placeholder="149" required></div>
                            <div class="mb-3"><label class="small fw-bold text-secondary">Category</label><select name="category" class="form-select bg-white text-dark border-secondary"><option value="Starter">Starter</option><option value="Main">Main Course</option><option value="Drink">Drinks & Shakes</option></select></div>
                            <button type="submit" class="btn btn-success w-100 fw-bold rounded-pill">Insert Row</button>
                        </form>
                    </div>
                </div>
                <div class="col-md-8"><div class="card p-3 border-0 shadow-sm clean-light-card" style="border-radius:12px;"><h5 class="fw-bold text-dark mb-3">Live Cost Configurations</h5><table class="table align-middle text-dark"><tbody>{inventory_rows}</tbody></table></div></div>
            </div>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        <script>setTimeout(() => {{ window.location.reload(); }}, 5000);</script>
    </body>
    </html>
    """

# ==============================================================================
# 👨‍🍳 WORKERS KITCHEN PANELS
# ==============================================================================
@app.route('/kitchen-login', methods=['GET', 'POST'])
def worker_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('kitchen'))

    error = ""
    if request.method == 'POST':
        if request.form.get('passcode') == WORKER_CREDENTIALS["passcode"]:
            session['worker_logged_in'] = True
            return redirect(url_for('kitchen'))
        error = "❌ Invalid Restaurant Staff Passcode!"
        
    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>DineQuick | Staff Entry</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">{GLOBAL_STYLE}</head>
    <body style="min-height:100vh; display:flex; align-items:center; justify-content:center;">
        <div class="card p-4 border-0 shadow-lg clean-light-card" style="max-width:380px; width:100%; border-radius:15px;">
            <h4 class="fw-bold text-center text-warning mb-3">👨‍🍳 Kitchen Staff Entry</h4>
            {f'<div class="alert alert-danger p-2 small text-center">{error}</div>' if error else ''}
            <form method="POST">
                <div class="mb-3">
                    <label class="small fw-bold text-dark mb-1">Staff Passcode</label>
                    <input type="password" name="passcode" class="form-control form-control-md text-center bg-white text-dark border-secondary" placeholder="••••••••" required>
                </div>
                <button type="submit" class="btn btn-warning w-100 fw-bold py-2 rounded-pill text-dark mb-2">Unlock Production Panel</button>
            </form>
            <div class="text-center mt-2">
                <a href="/reset-passcode/worker" class="text-decoration-none text-danger small fw-semibold">❓ Forgot Passcode?</a>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/kitchen')
@worker_login_required
def kitchen():
    active_orders = CustomerOrder.query.filter(CustomerOrder.status.in_(['Placed', 'Cooking', 'Served', 'Paid - Pending Verification'])).all()
    cards = ""
    for o in active_orders:
        if o.status == 'Paid - Pending Verification':
            border = "secondary"
            action_element = f'<div class="alert alert-warning text-center small p-2 fw-bold mb-0">💵 Awaiting Verification at Active Alert Desk Banners</div>'
        else:
            border = "danger" if o.status == 'Placed' else "warning" if o.status == 'Cooking' else "success"
            if o.status == 'Placed':
                action_element = f'<form action="/update_status/{o.id}/Cooking" method="POST"><button type="submit" class="btn btn-warning text-dark w-100 fw-bold py-2">🍳 Start Cooking</button></form>'
            elif o.status == 'Cooking':
                action_element = f'<form action="/update_status/{o.id}/Served" method="POST"><button type="submit" class="btn btn-success text-white w-100 fw-bold py-2">🚚 Deliver & Mark Served</button></form>'
            else: 
                action_element = f'<div class="text-center"><a href="/bill_generation/{o.id}" class="btn btn-info w-100 fw-bold py-2 text-dark shadow-sm">🧾 View Active Invoice</a></div>'

        order_type_badge = f'<span class="badge bg-warning text-dark">Takeaway</span>' if o.order_type == 'Takeaway' else f'<span class="badge bg-info text-dark">Table #{o.table_id}</span>'
        formatted_items = o.items_json.replace(", ", "<br>• ")

        cards += f"""
        <div class="col-md-4 mb-3">
            <div class="card p-3 shadow h-100 border-top border-4 clean-light-card" style="border-top-color: var(--bs-{border}) !important;">
                <div class="d-flex justify-content-between align-items-center mb-2">{order_type_badge}<span class="badge bg-{border}">{o.status}</span></div>
                <small class="text-muted">Account Client: <b>{o.username}</b></small><hr>
                <p class="fs-6 text-dark flex-grow-1">📋 <b>Order Payload Items:</b><br>• {formatted_items}</p>
                <div class="fw-bold text-info mb-3 small">Combined Total Tab: ₹{o.total_bill}</div>
                <div class="mt-auto">{action_element}</div>
            </div>
        </div>
        """
    if not cards: cards = "<div class='text-center w-100 py-5 text-muted'><h5>✨ Operational baseline quiet. No active pipeline items.</h5></div>"
    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>DineQuick | Workers Dashboard</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">{GLOBAL_STYLE}</head>
    <body>
        {get_navbar(1)}
        <div class="container">
            {get_live_alerts_html()}
            <div class="mb-4"><h2 class="fw-bold text-dark mb-0">👨‍🍳 Workers Kitchen Control Interface</h2></div>
            <div class="row g-3">{cards}</div>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            setTimeout(() => {{ window.location.reload(); }}, 5000);
        </script>
    </body>
    </html>
    """

@app.route('/update_status/<int:order_id>/<string:next_step>', methods=['POST'])
@worker_login_required
def step_pipeline(order_id, next_step):
    order = CustomerOrder.query.get(order_id)
    if order:
        order.status = next_step
        db.session.commit()
    return redirect(url_for('kitchen'))

@app.route('/kitchen/logout')
def kitchen_logout():
    session.pop('worker_logged_in', None)
    return redirect(url_for('welcome_page'))

# ==============================================================================
# HACKATHON RESET CONFIGURATION GATEWAY ROUTE
# ==============================================================================
@app.route('/reset-passcode/<string:role_type>', methods=['GET', 'POST'])
def handle_passcode_reset(role_type):
    global ADMIN_CREDENTIALS, WORKER_CREDENTIALS
    error = ""
    success_msg = ""
    
    if request.method == 'POST':
        user_token = request.form.get('recovery_token')
        new_secret = request.form.get('new_secret')
        
        if user_token == SECRET_RECOVERY_TOKEN:
            if role_type == "admin":
                ADMIN_CREDENTIALS["password"] = new_secret
                success_msg = "✅ Admin password reset successfully! Redirecting..."
            else:
                WORKER_CREDENTIALS["passcode"] = new_secret
                success_msg = "✅ Worker passcode reset successfully! Redirecting..."
        else:
            error = "❌ Invalid Hackathon Recovery Key Token!"

    target_redirect = "/admin-login" if role_type == "admin" else "/kitchen-login"
    autoforward_js = f"<script>setTimeout(function(){{ window.location.href='{target_redirect}'; }}, 2500);</script>" if success_msg else ""

    label_text = "New Administrative Password" if role_type == "admin" else "New Kitchen Staff Passcode"

    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>DineQuick | Account Recovery</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">{GLOBAL_STYLE}</head>
    <body style="min-height:100vh; display:flex; align-items:center; justify-content:center;">
        <div class="card p-4 border-0 shadow-lg clean-light-card" style="max-width:420px; width:100%; border-radius:15px;">
            <h4 class="fw-bold text-center text-danger mb-1">🔑 Prototype Recovery</h4>
            <p class="text-muted text-center small mb-3">Reset credentials for role: <span class="badge bg-dark">{role_type.upper()}</span></p>
            
            {f'<div class="alert alert-danger p-2 small text-center">{error}</div>' if error else ''}
            {f'<div class="alert alert-success p-2 small text-center">{success_msg}</div>' if success_msg else ''}
            
            <form method="POST">
                <div class="mb-2">
                    <label class="small fw-bold text-dark">Hackathon Verification Answer Token</label>
                    <input type="text" name="recovery_token" class="form-control form-control-sm bg-white text-dark" placeholder="Enter recovery token" required autocomplete="off">
                </div>
                <div class="mb-4">
                    <label class="small fw-bold text-dark">{label_text}</label>
                    <input type="password" name="new_secret" class="form-control form-control-sm bg-white text-dark" placeholder="Enter new value" required>
                </div>
                <button type="submit" class="btn btn-dark w-100 fw-bold py-2 rounded-pill">Override Configuration Keys</button>
            </form>
            <div class="text-center mt-3">
                <a href="/" class="text-decoration-none small text-secondary">← Back to Home</a>
            </div>
        </div>
        {autoforward_js}
    </body>
    </html>
    """

# ==============================================================================
# SCREEN 4: INVOICE GENERATOR & INTERACTIVE QR SCANNER GATEWAY
# ==============================================================================
@app.route('/bill_generation/<int:order_id>')
def generate_bill(order_id):
    order = CustomerOrder.query.get_or_404(order_id)
    items_list = order.items_json.split(", ")
    items_rows = "".join([f"<div class='d-flex justify-content-between my-1 text-muted'><span>{item}</span></div>" for item in items_list])
    qr_payload_url = f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=upi://pay?pa=dinequick@bank%26am={order.total_bill}%26tn=Order{order.id}"

    title_context = f"Counter Takeaway" if order.order_type == "Takeaway" else f"Table ID: #{order.table_id}"

    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>DineQuick | Invoice #{order.id}</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">{GLOBAL_STYLE}</head>
    <body class="py-5">
        <div class="container" style="max-width: 500px;">
            <div class="card p-4 shadow-sm border-0 clean-light-card">
                <div class="text-center mb-3"><h4 class="fw-bold text-dark mb-0">🧾 DINEQUICK COMBINED INVOICE</h4><small class="text-muted">{title_context} · Client: {order.username}</small></div>
                <hr><h6 class="fw-bold text-dark mb-2">Cumulative Items List:</h6><div class="mb-3">{items_rows}</div><hr>
                <div class="d-flex justify-content-between small text-muted mb-1"><span>Subtotal</span><span>₹{order.subtotal}</span></div>
                <div class="d-flex justify-content-between small text-muted mb-1"><span>CGST (2.5%)</span><span>₹{order.cgst}</span></div>
                <div class="d-flex justify-content-between small text-muted mb-2"><span>SGST (2.5%)</span><span>₹{order.sgst}</span></div>
                <div class="d-flex justify-content-between fw-bold fs-4 text-dark pt-2 border-top mb-4"><span>Grand Total Tab Due:</span><span class="text-success">₹{order.total_bill}</span></div>
                
                {"<div class='alert alert-warning text-center fw-bold small p-2 mb-0'>⏳ Awaiting payment verification check from managers...</div>" if order.status == 'Paid - Pending Verification' else f'<button class="btn btn-success w-100 py-3 fw-bold rounded-pill fs-5 shadow text-white" data-bs-toggle="modal" data-bs-target="#paymentModal"><i class="fa-solid fa-qrcode me-2"></i> Close Tab & Scan Pay</button>'}
            </div>
        </div>
        <div class="modal fade" id="paymentModal" tabIndex="-1" aria-hidden="true" data-bs-backdrop="static">
            <div class="modal-dialog modal-dialog-centered" style="max-width: 400px;">
                <div class="modal-content border-0 shadow-lg text-center p-4">
                    <div class="modal-header border-0 justify-content-center pt-2 pb-0"><h5 class="fw-bold text-dark">Contactless UPI Scanner</h5></div>
                    <div class="modal-body">
                        <div class="bg-light p-3 rounded-3 d-inline-block shadow-sm my-2"><img src="{qr_payload_url}" alt="UPI Scanner Code" class="img-fluid rounded"></div>
                        <div class="fs-4 fw-bold text-success mt-2">₹{order.total_bill}</div>
                    </div>
                    <div class="modal-footer border-0 d-grid gap-2">
                        <button class="btn btn-success p-2.5 fw-bold rounded-pill text-white" onclick="simulatePaymentSettle()">Confirm Payment Success</button>
                    </div>
                </div>
            </div>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            function simulatePaymentSettle() {{
                fetch('/api/pay_invoice/{order.id}', {{ method: 'POST' }}).then(res => res.json()).then(data => {{
                    if(data.success) {{ alert("🚀 Payment notice submitted! Awaiting staff audit verification loop clearance."); window.location.href = "/table/" + {order.table_id}; }}
                }});
            }}
        </script>
    </body>
    </html>
    """

# ==============================================================================
# 📢 INJECT STAGED VERIFICATION NOTIFICATIONS ON CUSTOMER CHECKOUT DISPATCH
# ==============================================================================
@app.route('/api/pay_invoice/<int:order_id>', methods=['POST'])
def finalize_invoice_payment(order_id):
    global LIVE_NOTIFICATIONS, NOTIFICATION_COUNTER
    order = CustomerOrder.query.get(order_id)
    if order:
        order.status = 'Paid - Pending Verification'
        
        if order.table_id > 0:
            msg_text = f"Customer '{order.username}' at Table #{order.table_id} submitted a payment of ₹{order.total_bill}."
        else:
            msg_text = f"Takeaway Customer '{order.username}' submitted a payment of ₹{order.total_bill}."
            
        NOTIFICATION_COUNTER += 1
        LIVE_NOTIFICATIONS.append({
            "id": NOTIFICATION_COUNTER,
            "order_id": order_id,
            "text": msg_text
        })
        
        db.session.commit()
    return jsonify({"success": True})

# ==============================================================================
# 🍛 CUMULATIVE MERGING ORDER ENGINE
# ==============================================================================
@app.route('/api/submit_order', methods=['POST'])
def handle_api_order():
    data = request.get_json()
    table_id = data.get('table_id')
    cart_data = data.get('cart_data')
    
    new_round_strings = []
    round_subtotal = 0
    for id, details in cart_data.items():
        round_subtotal += details['price'] * details['qty']
        new_round_strings.append(f"{details['qty']}x {details['name']} (₹{details['price']})")
    
    round_items_json = ", ".join(new_round_strings)
    order_type = 'Takeaway' if table_id == 0 else 'Dine-In'

    existing_order = None
    if table_id > 0:
        existing_order = CustomerOrder.query.filter(
            CustomerOrder.table_id == table_id,
            CustomerOrder.status.in_(['Placed', 'Cooking', 'Served'])
        ).order_by(CustomerOrder.id.desc()).first()

    if existing_order:
        existing_order.items_json += ", " + round_items_json
        existing_order.subtotal += round_subtotal
        existing_order.cgst = round(existing_order.subtotal * 0.025, 2)
        existing_order.sgst = round(existing_order.subtotal * 0.025, 2)
        existing_order.total_bill = round(existing_order.subtotal + existing_order.cgst + existing_order.sgst, 2)
        existing_order.status = 'Placed'
    else:
        cgst = round(round_subtotal * 0.025, 2)
        sgst = round(round_subtotal * 0.025, 2)
        grand_total = round(round_subtotal + cgst + sgst, 2)
        
        new_order = CustomerOrder(
            table_id=table_id, 
            username=session.get('username', 'Guest'), 
            items_json=round_items_json, 
            subtotal=round_subtotal, 
            cgst=cgst, 
            sgst=sgst, 
            total_bill=grand_total, 
            status='Placed',
            order_type=order_type
        )
        db.session.add(new_order)

    if table_id > 0:
        table = RestaurantTable.query.get(table_id)
        if table: 
            table.status = 'Seated'
        
    db.session.commit()
    return jsonify({"success": True})

# ==============================================================================
# 🚀 RUNTIME INITIALIZATION WITH AUTO-MIGRATION PATCH
# ==============================================================================
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        try:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE customer_order ADD COLUMN order_type VARCHAR(20) DEFAULT 'Dine-In';"))
                conn.commit()
        except Exception:
            pass

        if MenuItem.query.first() is None:
            db.session.add(MenuItem(name="Onion Rings", price=199.0, category="Starter"))
            db.session.add(MenuItem(name="Wings (6 pc)", price=349.0, category="Starter"))
            db.session.add(MenuItem(name="Dal Makhani", price=429.0, category="Main"))
            db.session.add(MenuItem(name="Paneer Tikka", price=379.0, category="Main"))
            db.session.add(MenuItem(name="Mango Lassi", price=99.0, category="Drink"))
            db.session.commit()
        if RestaurantTable.query.first() is None:
            for t_id in range(1, 9): db.session.add(RestaurantTable(id=t_id, status='Vacant'))
            db.session.commit()
    app.run(debug=True, port=8080)
