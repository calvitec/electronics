from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash
from datetime import datetime, timedelta
import os
import uuid
import json
import requests
import traceback
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.permanent_session_lifetime = timedelta(days=7)

# ================================================================
# ===== VERCEL COMPATIBILITY =====
# ================================================================

# Use /tmp for all file operations on Vercel
TMP_DIR = '/tmp'
JSON_DIR = os.path.join(TMP_DIR, 'data')

# Create directories
try:
    os.makedirs(JSON_DIR, exist_ok=True)
    os.makedirs(os.path.join(TMP_DIR, 'static/uploads'), exist_ok=True)
except Exception as e:
    print(f"Directory creation error: {e}")

def get_json_path(filename):
    """Get path for JSON files in /tmp"""
    return os.path.join(JSON_DIR, filename)

def load_json(filename):
    """Load JSON from /tmp"""
    try:
        path = get_json_path(filename)
        if os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
        # Create default empty file
        with open(path, 'w') as f:
            json.dump([], f)
        return []
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return []

def save_json(filename, data):
    """Save JSON to /tmp"""
    try:
        path = get_json_path(filename)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving {filename}: {e}")
        return False

# Initialize JSON files
for filename in ['products.json', 'bundles.json', 'orders.json']:
    load_json(filename)

# ================================================================
# ===== SAMPLE DATA =====
# ================================================================

def get_sample_products():
    """Return sample products if no data exists"""
    return [
        {
            'id': '1',
            'name': 'iPhone 15 Pro Max',
            'price': 150000,
            'cost_price': 120000,
            'image': 'https://via.placeholder.com/300x300/000/fff?text=iPhone',
            'category': 'Phones',
            'description': 'Latest iPhone with amazing features',
            'rating': 4.8,
            'reviews': 120,
            'badge': 'Best Seller',
            'stock': 50,
            'original_price': 165000,
            'specs': ['6.7" Display', '48MP Camera', 'A17 Pro Chip']
        },
        {
            'id': '2',
            'name': 'MacBook Pro M3',
            'price': 250000,
            'cost_price': 200000,
            'image': 'https://via.placeholder.com/300x300/000/fff?text=MacBook',
            'category': 'Laptops',
            'description': 'Powerful laptop for professionals',
            'rating': 4.9,
            'reviews': 85,
            'badge': 'New',
            'stock': 30,
            'original_price': 280000,
            'specs': ['14" Display', 'M3 Chip', '16GB RAM']
        }
    ]

# ================================================================
# ===== DATABASE FUNCTIONS =====
# ================================================================

def load_products():
    """Load products from JSON"""
    products = load_json('products.json')
    if not products:
        products = get_sample_products()
        save_json('products.json', products)
    return products

def load_orders():
    """Load orders from JSON"""
    return load_json('orders.json')

def get_cart():
    """Get cart from session"""
    return session.get('cart', {})

# ================================================================
# ===== ROUTES =====
# ================================================================

@app.route('/')
def index():
    try:
        products = load_products()
        return render_template('index.html', products=products)
    except Exception as e:
        print(f"Error in index: {e}")
        return render_template_string("""
            <h1>📱 Price Point</h1>
            <p>Welcome to Price Point Electronics Shop</p>
            <p><a href="/api/status">Check Status</a></p>
        """)

@app.route('/api/status')
def api_status():
    try:
        products = load_products()
        orders = load_orders()
        return jsonify({
            'status': 'ok',
            'products': len(products),
            'orders': len(orders),
            'environment': 'vercel',
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/products')
def api_products():
    try:
        products = load_products()
        return jsonify(products)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/orders')
def api_orders():
    try:
        orders = load_orders()
        return jsonify(orders)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ================================================================
# ===== CART ROUTES =====
# ================================================================

@app.route('/add-to-cart/<product_id>', methods=['POST'])
def add_to_cart(product_id):
    try:
        cart = get_cart()
        cart[product_id] = cart.get(product_id, 0) + 1
        session['cart'] = cart
        session.modified = True
        return jsonify({
            'success': True,
            'message': 'Added to cart',
            'count': sum(cart.values())
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/cart')
def cart_page():
    try:
        cart = get_cart()
        products = load_products()
        cart_items = []
        subtotal = 0
        
        for product_id, quantity in cart.items():
            for product in products:
                if str(product.get('id')) == str(product_id):
                    item_total = product.get('price', 0) * quantity
                    cart_items.append({
                        'id': product_id,
                        'name': product.get('name', 'Product'),
                        'price': product.get('price', 0),
                        'quantity': quantity,
                        'item_total': item_total
                    })
                    subtotal += item_total
                    break
        
        shipping = 0 if subtotal >= 50000 else 800
        total = subtotal + shipping
        
        return render_template('cart.html',
            cart_items=cart_items,
            subtotal=subtotal,
            shipping=shipping,
            total=total
        )
    except Exception as e:
        return render_template_string(f"<h1>Cart Error</h1><p>{str(e)}</p>")

@app.route('/checkout')
def checkout_page():
    cart = get_cart()
    if not cart:
        flash('Cart is empty', 'warning')
        return redirect(url_for('index'))
    return render_template('checkout.html')

@app.route('/place-order', methods=['POST'])
def place_order():
    try:
        cart = get_cart()
        if not cart:
            return jsonify({'success': False, 'message': 'Cart is empty'}), 400
        
        # Generate order ID
        order_id = f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        
        # Get customer data
        data = request.get_json() or request.form
        customer_name = data.get('customer_name', 'Customer')
        
        order_data = {
            'order_id': order_id,
            'customer_name': customer_name,
            'customer_email': data.get('customer_email', ''),
            'customer_phone': data.get('customer_phone', ''),
            'customer_address': data.get('customer_address', ''),
            'items': list(cart.items()),
            'total': data.get('total', 0),
            'status': 'pending',
            'created_at': datetime.utcnow().isoformat()
        }
        
        # Save order
        orders = load_orders()
        orders.insert(0, order_data)
        save_json('orders.json', orders)
        
        # Clear cart
        session['cart'] = {}
        session.modified = True
        
        return jsonify({
            'success': True,
            'order_id': order_id,
            'message': 'Order placed successfully'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ================================================================
# ===== ERROR HANDLERS =====
# ================================================================

@app.errorhandler(404)
def page_not_found(e):
    return render_template_string("""
        <h1>404 - Page Not Found</h1>
        <p>The page you're looking for doesn't exist.</p>
        <a href="/">Go Home</a>
    """), 404

@app.errorhandler(500)
def internal_server_error(e):
    return jsonify({
        'error': 'Internal Server Error',
        'message': 'Something went wrong. Please try again later.'
    }), 500

# ================================================================
# ===== MAIN =====
# ================================================================

if __name__ == '__main__':
    print("="*60)
    print("📱 Price Point - Vercel Ready")
    print("="*60)
    print("🚀 Starting server...")
    app.run(debug=False, host='0.0.0.0', port=5000)
