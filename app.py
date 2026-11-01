import os
from decimal import Decimal
from functools import wraps
from pathlib import Path

import click
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import or_
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-only-change-before-deployment')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + str(BASE_DIR / 'phone_shop.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('COOKIE_SECURE') == '1'
db = SQLAlchemy(app)
csrf = CSRFProtect(app)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    description = db.Column(db.Text, nullable=False)
    stock_quantity = db.Column(db.Integer, nullable=False, default=0)
    condition = db.Column(db.String(30), nullable=False)
    storage = db.Column(db.String(30), nullable=False)
    colour = db.Column(db.String(50), nullable=False)
    battery_health = db.Column(db.Integer, nullable=False, default=100)
    grade = db.Column(db.String(10))
    phone_picture = db.Column(db.String(500), nullable=False, default='')

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    userphone = db.Column(db.String(50))
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    cart = db.relationship('Cart', back_populates='user', uselist=False, cascade='all, delete-orphan')

class Cart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    user = db.relationship('User', back_populates='cart')
    items = db.relationship('CartItem', back_populates='cart', cascade='all, delete-orphan')

class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.Integer, db.ForeignKey('cart.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    cart = db.relationship('Cart', back_populates='items')
    product = db.relationship('Product')
    __table_args__ = (db.UniqueConstraint('cart_id', 'product_id', name='uq_cart_product'),)

@app.context_processor
def shared_context():
    user = db.session.get(User, session.get('user_id')) if session.get('user_id') else None
    return {'current_user': user}

def login_required(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        if not session.get('user_id') or not db.session.get(User, session['user_id']):
            flash('Please sign in first.', 'warning')
            return redirect(url_for('login'))
        return func(*args, **kwargs)
    return wrapped

def admin_required(func):
    @wraps(func)
    @login_required
    def wrapped(*args, **kwargs):
        user = db.session.get(User, session['user_id'])
        if not user.is_admin:
            flash('Admin access required.', 'error')
            return redirect(url_for('home'))
        return func(*args, **kwargs)
    return wrapped

def own_cart():
    cart = Cart.query.filter_by(user_id=session['user_id']).first()
    if cart is None:
        cart = Cart(user_id=session['user_id'])
        db.session.add(cart)
        db.session.commit()
    return cart

def read_product_form(product):
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    storage = request.form.get('storage', '').strip()
    colour = request.form.get('colour', '').strip()
    condition = request.form.get('condition', '')
    grade = request.form.get('grade', '').strip() or None
    picture = request.form.get('phone_picture', '').strip()
    try:
        price = Decimal(request.form.get('price', ''))
        stock = int(request.form.get('stock_quantity', ''))
        battery = int(request.form.get('battery_health', ''))
        if not price.is_finite() or price < 0 or price.as_tuple().exponent < -2 or stock < 0 or not 0 <= battery <= 100:
            raise ValueError
    except (ValueError, ArithmeticError):
        return 'Enter a valid price, stock quantity and battery health.'
    if not name or not description or not storage or not colour or condition not in ('New', 'Refurbished'):
        return 'Complete all required fields.'
    if len(name) > 100 or len(storage) > 30 or len(colour) > 50 or len(picture) > 500 or (grade and len(grade) > 10):
        return 'One of the fields is too long.'
    for key, value in {'name':name, 'description':description, 'storage':storage, 'colour':colour, 'condition':condition, 'grade':grade, 'phone_picture':picture, 'price':price, 'stock_quantity':stock, 'battery_health':battery}.items():
        setattr(product, key, value)
    return None

@app.route('/')
def home():
    featured = Product.query.order_by(Product.id.desc()).limit(4).all()
    return render_template('index.html', featured=featured)

@app.route('/Products')
def products():
    query = Product.query
    search = request.args.get('search', '').strip()
    price = request.args.get('price', '')
    condition = request.args.get('condition', '')
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))
    if price == 'under500':
        query = query.filter(Product.price < 500)
    elif price == '500-800':
        query = query.filter(Product.price >= 500, Product.price < 800)
    elif price == '800-1000':
        query = query.filter(Product.price >= 800, Product.price < 1000)
    elif price == 'over1000':
        query = query.filter(Product.price >= 1000)
    if condition in ('New', 'Refurbished'):
        query = query.filter(Product.condition == condition)
    return render_template('products.html', products=query.order_by(Product.id.desc()).all(), search=search, price=price, condition=condition)

@app.route('/Products-details/<int:id>')
def product_details(id):
    return render_template('product_details.html', product=Product.query.get_or_404(id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        phone = request.form.get('userphone', '').strip()
        if not username or '@' not in email or len(password) < 8:
            flash('Enter a username, valid email and password of at least 8 characters.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('An account with that email already exists.', 'error')
        else:
            user = User(username=username, email=email, password_hash=generate_password_hash(password), userphone=phone)
            db.session.add(user)
            db.session.flush()
            db.session.add(Cart(user_id=user.id))
            db.session.commit()
            flash('Account created. Please sign in.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form.get('email', '').strip().lower()).first()
        if user and check_password_hash(user.password_hash, request.form.get('password', '')):
            session.clear()
            session['user_id'] = user.id
            flash('Welcome back!', 'success')
            return redirect(url_for('admin') if user.is_admin else url_for('home'))
        flash('Invalid email or password.', 'error')
    return render_template('login.html')

@app.post('/logout')
@login_required
def logout():
    session.clear()
    flash('Signed out.', 'success')
    return redirect(url_for('home'))

@app.route('/customers')
@login_required
def customers():
    return render_template('customer.html', user=db.session.get(User, session['user_id']))

@app.route('/edit_details', methods=['GET', 'POST'])
@login_required
def edit_details():
    user = db.session.get(User, session['user_id'])
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        if not username or '@' not in email:
            flash('Enter a username and valid email.', 'error')
        elif User.query.filter(User.email == email, User.id != user.id).first():
            flash('Email already in use.', 'error')
        else:
            user.username = username
            user.email = email
            user.userphone = request.form.get('userphone', '').strip()
            db.session.commit()
            flash('Profile updated.', 'success')
            return redirect(url_for('customers'))
    return render_template('edit_details.html', user=user)

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    user = db.session.get(User, session['user_id'])
    if request.method == 'POST':
        old = request.form.get('old_password', '')
        new = request.form.get('new_password', '')
        if not check_password_hash(user.password_hash, old):
            flash('Current password is incorrect.', 'error')
        elif len(new) < 8 or check_password_hash(user.password_hash, new):
            flash('Choose a different password with at least 8 characters.', 'error')
        else:
            user.password_hash = generate_password_hash(new)
            db.session.commit()
            flash('Password changed.', 'success')
            return redirect(url_for('customers'))
    return render_template('change_password.html')

@app.route('/cart')
@login_required
def cart():
    items = own_cart().items
    total = sum((item.product.price * item.quantity for item in items), Decimal('0.00'))
    return render_template('cart.html', items=items, total=total)

@app.post('/add_to_cart/<int:id>')
@login_required
def add_to_cart(id):
    product = Product.query.get_or_404(id)
    cart = own_cart()
    item = CartItem.query.filter_by(cart_id=cart.id, product_id=product.id).first()
    quantity = item.quantity if item else 0
    if quantity >= product.stock_quantity:
        flash('Not enough stock available.', 'error')
    elif item:
        item.quantity += 1
        db.session.commit()
        flash('Quantity updated.', 'success')
    else:
        db.session.add(CartItem(cart_id=cart.id, product_id=product.id, quantity=1))
        db.session.commit()
        flash('Added to cart.', 'success')
    return redirect(url_for('cart'))

@app.post('/cart/quantity/<int:id>/<action>')
@login_required
def change_quantity(id, action):
    item = CartItem.query.join(Cart).filter(CartItem.id == id, Cart.user_id == session['user_id']).first_or_404()
    if action == 'plus':
        if item.quantity < item.product.stock_quantity:
            item.quantity += 1
        else:
            flash('Stock limit reached.', 'warning')
    elif action == 'minus':
        if item.quantity > 1:
            item.quantity -= 1
    else:
        flash('Invalid action.', 'error')
        return redirect(url_for('cart'))
    db.session.commit()
    return redirect(url_for('cart'))

@app.post('/cart/remove/<int:id>')
@login_required
def remove_item(id):
    item = CartItem.query.join(Cart).filter(CartItem.id == id, Cart.user_id == session['user_id']).first_or_404()
    db.session.delete(item)
    db.session.commit()
    flash('Item removed.', 'success')
    return redirect(url_for('cart'))

@app.route('/admin')
@admin_required
def admin():
    return render_template('admin.html', products=Product.query.order_by(Product.id.desc()).all())

@app.route('/add_products', methods=['GET', 'POST'])
@admin_required
def add_products():
    if request.method == 'POST':
        product = Product()
        error = read_product_form(product)
        if error:
            flash(error, 'error')
        else:
            db.session.add(product)
            db.session.commit()
            flash('Product added.', 'success')
            return redirect(url_for('admin'))
    return render_template('product_form.html', product=None, heading='Add product')

@app.route('/edit_products/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_products(id):
    product = Product.query.get_or_404(id)
    if request.method == 'POST':
        error = read_product_form(product)
        if error:
            flash(error, 'error')
        else:
            db.session.commit()
            flash('Product updated.', 'success')
            return redirect(url_for('admin'))
    return render_template('product_form.html', product=product, heading='Edit product')

@app.post('/delete/<int:id>')
@admin_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    if CartItem.query.filter_by(product_id=id).first():
        flash('Cannot delete a product that is currently in a cart. Set stock to zero instead.', 'warning')
    else:
        db.session.delete(product)
        db.session.commit()
        flash('Product deleted.', 'success')
    return redirect(url_for('admin'))

@app.cli.command('init-db')
def init_db():
    db.create_all()
    click.echo('Database tables created.')

@app.cli.command('create-admin')
def create_admin():
    email = os.environ.get('ADMIN_EMAIL', '').strip().lower()
    password = os.environ.get('ADMIN_PASSWORD', '')
    if '@' not in email or len(password) < 12:
        raise click.ClickException('Set ADMIN_EMAIL and ADMIN_PASSWORD (12+ characters) in your environment.')
    user = User.query.filter_by(email=email).first()
    if user:
        user.is_admin = True
        user.password_hash = generate_password_hash(password)
    else:
        user = User(username='Administrator', email=email, password_hash=generate_password_hash(password), is_admin=True)
        db.session.add(user)
        db.session.flush()
        db.session.add(Cart(user_id=user.id))
    db.session.commit()
    click.echo('Admin account created or updated.')

if __name__ == '__main__':
    app.run(debug=True)
