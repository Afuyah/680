from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_user, logout_user, current_user, login_required
from sqlalchemy import func
from app.models import User, db, Role, Sale, Product
from werkzeug.security import generate_password_hash, check_password_hash
import logging

auth_bp = Blueprint('auth', __name__)

# Create a logger instance
logger = logging.getLogger(__name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    logger.info("Login route accessed.")
    if request.method == 'POST':
        # Extract JSON or form data
        if request.is_json:
            data = request.get_json()
            username = data.get('username')
            password = data.get('password')
        else:
            username = request.form.get('username')
            password = request.form.get('password')

        logger.info(f"Login attempt for username: {username}")

        # Convert username to lowercase for case-insensitive matching
        username = username.strip().lower()

        # Query user from database
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            logger.info(f"User {username} logged in successfully.")

            # Redirect based on user role
            redirect_url = url_for('auth.admin_dashboard') if user.is_admin() else url_for('sales.sales_screen')
            
            # For AJAX requests
            if request.is_json:
                return jsonify({'success': True, 'redirect_url': redirect_url}), 200
            return redirect(redirect_url)

        logger.warning(f"Login failed for username: {username}. Invalid credentials.")
        error_field = 'username' if not user else 'password'
        if request.is_json:
            return jsonify({'success': False, 'error': error_field}), 401
        else:
            flash('Invalid username or password.', category='error')
            return redirect(url_for('auth.login'))

    return render_template('auth/login.html')

@auth_bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    logger.info("Change password route accessed.")
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        # Validate current password
        if not current_user.check_password(current_password):
            flash('Current password is incorrect.', category='error')
            logger.warning(f"User {current_user.username} provided incorrect current password.")
            return redirect(url_for('auth.change_password'))

        # Validate new password confirmation
        if new_password != confirm_password:
            flash('New passwords do not match.', category='error')
            logger.warning("New password confirmation did not match.")
            return redirect(url_for('auth.change_password'))

        if len(new_password) < 5:  
            flash('New password must be at least 5 characters long.', category='error')
            logger.warning("New password length is insufficient.")
            return redirect(url_for('auth.change_password'))

        # Set the new password
        current_user.set_password(new_password)
        db.session.commit()
        flash('Your password has been updated successfully!', category='success')
        logger.info(f"User {current_user.username} updated their password.")

        return redirect(url_for('auth.admin_dashboard') if current_user.is_admin() else url_for('auth.cashier_dashboard'))

    template_name = 'auth/admin_change_password.html' if current_user.is_admin() else 'auth/change_password.html'
    return render_template(template_name)

@auth_bp.route('/logout')
@login_required
def logout():
    logger.info(f"User {current_user.username} logged out.")
    
    # Clear the session (including cart data)
    session.clear()
    
    logout_user()  # Log out the user
    flash('Logged out successfully.', 'success')
    return redirect(url_for('home.index'))

@auth_bp.route('/admin_dashboard')
@login_required
def admin_dashboard():
    logger.info(f"Admin dashboard accessed by user {current_user.username}.")
    if not current_user.is_admin():
        flash('Access denied. You do not have permission to access this page.', 'warning')
        logger.warning(f"User {current_user.username} attempted to access admin dashboard without permissions.")
        return redirect(url_for('home.index'))

    total_sales = db.session.query(func.sum(Sale.total)).scalar() or 0
    total_transactions = db.session.query(func.count(Sale.id)).scalar() or 0
    total_revenue = db.session.query(func.sum(Sale.total)).scalar() or 0
    recent_sales = Sale.query.order_by(Sale.date.desc()).limit(5).all()
    low_stock_threshold = 10
    low_stock_products = Product.query.filter(Product.stock <= low_stock_threshold).all()

    return render_template(
        'auth/admin_dashboard.html',
        total_sales=total_sales,
        total_transactions=total_transactions,
        total_revenue=total_revenue,
        recent_sales=recent_sales,
        low_stock_products=low_stock_products
    )

@auth_bp.route('/cashier_dashboard')
@login_required
def cashier_dashboard():
    logger.info(f"Cashier dashboard accessed by user {current_user.username}.")
    if not current_user.is_cashier():
        flash('Access denied. You do not have permission to access this page.', 'warning')
        logger.warning(f"User {current_user.username} attempted to access cashier dashboard without permissions.")
        return redirect(url_for('home.index'))

    return render_template('sales.html')

@auth_bp.route('/user_management', methods=['GET'])
@login_required
def user_management():
    logger.info(f"User management accessed by user {current_user.username}.")
    if not current_user.is_admin():
        flash('Access denied. You do not have permission to access this page.', 'warning')
        logger.warning(f"User {current_user.username} attempted to access user management without permissions.")
        return redirect(url_for('home.index'))

    users = User.query.all()
    return render_template('auth/user_management.html', users=users)

@auth_bp.route('/add_user', methods=['GET', 'POST'])
@login_required
def add_user():
    logger.info(f"Add user route accessed by user {current_user.username}.")
    if not current_user.is_admin():
        flash('Access denied. You do not have permission to access this page.', 'warning')
        logger.warning(f"User {current_user.username} attempted to access add user without permissions.")
        return redirect(url_for('home.index'))

    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = request.form['password']
        role = request.form['role']

        if username.isdigit():
            flash('Username cannot contain only numbers.', 'danger')
            logger.warning("Invalid username attempt: only numbers.")
            return render_template('auth/add_user.html')

        if role.upper() not in Role.__members__:
            flash('Invalid role selected.', 'danger')
            logger.warning("Invalid role selected during user creation.")
            return render_template('auth/add_user.html')

        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            logger.warning("Username already exists during user creation.")
            return render_template('auth/add_user.html')

        new_user = User(username=username, role=Role[role.upper()])
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        flash(f'{role.capitalize()} "{username}" added successfully!', 'success')
        logger.info(f"Admin added user: {username}.")
        return redirect(url_for('auth.user_management'))

    return render_template('auth/add_user.html')

@auth_bp.route('/edit_user/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_user(id: int):
    logger.info(f"Edit user route accessed by user {current_user.username}.")
    if not current_user.is_admin():
        flash('Access denied. You do not have permission to access this page.', 'warning')
        logger.warning(f"User {current_user.username} attempted to access edit user without permissions.")
        return redirect(url_for('home.index'))

    user = User.query.get_or_404(id)

    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        role = request.form['role']

        if username.isdigit():
            flash('Username cannot contain only numbers.', 'danger')
            logger.warning("Invalid username attempt during edit: only numbers.")
            return render_template('auth/edit_user.html', user=user, Role=Role)

        if role.upper() not in Role.__members__:
            flash('Invalid role selected.', 'danger')
            logger.warning("Invalid role selected during user edit.")
            return render_template('auth/edit_user.html', user=user, Role=Role)

        if User.query.filter_by(username=username).first() and username != user.username:
            flash('Username already exists.', 'danger')
            logger.warning("Username already exists during user edit.")
            return render_template('auth/edit_user.html', user=user, Role=Role)

        user.username = username
        user.role = Role[role.upper()]
        
        db.session.commit()

        flash(f'User "{username}" updated successfully!', 'success')
        logger.info(f"User updated: {username}.")
        return redirect(url_for('auth.user_management'))

    return render_template('auth/edit_user.html', user=user, Role=Role)
