from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, session
from flask_login import  current_user, login_required
from app.models import db, Product, Sale, CartItem, Category
from app import  socketio
from flask_socketio import emit
from collections import defaultdict
from sqlalchemy import func
from datetime import datetime

from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


sales_bp = Blueprint('sales', __name__)

# Helper function to check low stock
def check_low_stock(product):
    return product.stock < 5


@sales_bp.route('/sales')
@login_required
def sales_screen():
    categories = Category.query.all()  # Fetch all categories
    return render_template('sales.html', categories=categories)


# Route for cashier to view sales screen
@sales_bp.route('/api/products/<int:category_id>', methods=['GET'])
@login_required
def get_products_by_category(category_id):
    try:
        # Fetch products by category, including all relevant fields
        products = Product.query.filter_by(category_id=category_id).all()  
        if not products:
            return jsonify({'message': 'No products found in this category'}), 404

        # Constructing the product list to include necessary fields
        product_list = [{
            'id': product.id,
            'name': product.name,
            'selling_price': float(product.selling_price) if product.selling_price is not None else None,  # Ensure it's a float
            'combination_price': float(product.combination_price) if product.combination_price is not None else None,  # Ensure it's a float
            'combination_unit_price': float(product.combination_unit_price) if product.combination_unit_price is not None else None,  # Ensure it's a float
            'combination_size': product.combination_size,
            'stock': product.stock
        } for product in products]

        return jsonify({'products': product_list})

    except Exception as e:
        logging.error(f"Error fetching products for category {category_id}: {e}")
        return jsonify({'error': 'An error occurred while fetching products.'}), 500


@sales_bp.route('/add_to_cart', methods=['POST'])
@login_required
def add_to_cart():
    data = request.json
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)  # Default to 1 if not provided

    product = Product.query.get(product_id)
    if not product:
        return jsonify({'success': False, 'message': 'Product not found'}), 404

    # Check stock availability
    if product.stock < quantity:
        return jsonify({'success': False, 'message': 'Insufficient stock'}), 400

    # Calculate subtotal based on quantity
    subtotal = 0
    if quantity < product.combination_size:
        subtotal = product.selling_price * quantity
    else:
        subtotal = (quantity // product.combination_size) * product.combination_price
        if quantity % product.combination_size != 0:
            subtotal += (quantity % product.combination_size) * product.selling_price

    # Initialize the cart in session if it doesn't exist
    if 'cart' not in session:
        session['cart'] = []

    # Add or update the item in the session cart
    cart = session['cart']
    for item in cart:
        if item['product_id'] == product_id:
            item['quantity'] += quantity
            item['subtotal'] += subtotal
            break
    else:
        cart.append({
            'product_id': product.id,
            'product_name': product.name,
            'quantity': quantity,
            'selling_price': product.selling_price,
            'combination_price': product.combination_price,
            'subtotal': subtotal
        })

    session['cart'] = cart  # Update session cart
    return jsonify({'success': True, 'cart': session['cart']})

    
@sales_bp.route('/checkout', methods=['POST'])
@login_required
def checkout():
    data = request.json
    cart = data.get('cart', [])
    payment_method = data.get('payment_method', 'cash')
    customer_name = data.get('customer_name')

    if not cart:
        return jsonify({'success': False, 'message': 'Cart is empty'}), 400

    total_amount = 0
    total_cost = 0  # Initialize total cost for profit calculation
    items_to_update_stock = []

    for item in cart:
        product = Product.query.get(item['id'])
        if product is None:
            return jsonify({'success': False, 'message': 'Product not found'}), 404

        quantity = item['quantity']

        # Check stock availability before any calculations
        if product.stock < quantity:
            return jsonify({'success': False, 'message': f'Insufficient stock for {product.name}'}), 400

        # Calculate subtotal using combination-first approach
        full_combinations = quantity // product.combination_size
        remaining_units = quantity % product.combination_size

        # Calculate cost for full combinations
        subtotal = full_combinations * product.combination_price

        # Calculate cost for remaining units and choose the cheaper option
        individual_remainder_cost = remaining_units * product.selling_price
        additional_combination_cost = product.combination_price  # Cost of an extra combination

        # Add the cheaper of the two options for the remaining units
        subtotal += min(individual_remainder_cost, additional_combination_cost)

        total_amount += subtotal

        # Calculate the total cost for profit calculation
        total_cost += (full_combinations * product.cost_price * product.combination_size) + (remaining_units * product.cost_price)

        items_to_update_stock.append((product, quantity))

    # Create the Sale object with profit calculation
    sale = Sale(
        date=datetime.utcnow(),
        total=total_amount,
        payment_method=payment_method,
        customer_name=customer_name if payment_method == 'credit' else None,
    )
    
    # Calculate profit
    sale_profit = total_amount - total_cost  # Profit = Total Sales - Total Cost
    sale.profit = sale_profit  # Set the profit calculated for this sale
    db.session.add(sale)

    try:
        # Commit the sale to get a valid sale_id
        db.session.commit()

        # Update stock and create CartItem records
        for product, quantity in items_to_update_stock:
            product.stock -= quantity
            cart_item = CartItem(product_id=product.id, quantity=quantity, sale_id=sale.id)
            db.session.add(cart_item)

        db.session.commit()

        # Emit real-time updates after successful commit
        for product, quantity in items_to_update_stock:
            socketio.emit('stock_updated', {'id': product.id, 'name': product.name, 'stock': product.stock}, broadcast=True)
            if check_low_stock(product):  # Check for low stock
                socketio.emit('low_stock_alert', {'product_name': product.name, 'stock': product.stock}, broadcast=True)

        return jsonify({'success': True, 'message': 'Sale completed successfully', 'profit': sale_profit})
    except IntegrityError as e:
        db.session.rollback()
        logging.error(f'Integrity error during transaction: {e}')
        return jsonify({'success': False, 'message': 'Integrity error during transaction'}), 400
    except Exception as e:
        db.session.rollback()
        logging.error(f'Error during transaction: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


@sales_bp.route('/api/todays-total-sales', methods=['GET'])
@login_required
def todays_total_sales():
    # Get today's date
    today = datetime.today().date()
    
    try:
        # Query for today's total sales and transaction count
        total_sales = db.session.query(func.coalesce(func.sum(Sale.total), 0)).filter(func.date(Sale.date) == today).scalar()
        total_transactions = db.session.query(func.count(Sale.id)).filter(func.date(Sale.date) == today).scalar()
        
        # Return total sales as JSON
        return jsonify({
            'total_sales': round(total_sales, 2),
            'total_transactions': total_transactions
        })

    except Exception as e:
        logging.error(f"Error fetching today's sales: {e}")
        return jsonify({'error': 'Failed to fetch sales data'}), 500


from collections import Counter

@sales_bp.route('/reports/daily', methods=['GET'])
@login_required
def daily_sales_report():
    date_str = request.args.get('date', datetime.today().date().strftime('%Y-%m-%d'))
    
    try:
        report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash("Invalid date format. Please use YYYY-MM-DD.", "danger")
        return redirect(url_for('sales_bp.daily_sales_report'))

    # Query sales data for the selected date
    sales = Sale.query.filter(func.date(Sale.date) == report_date).all()
    
    if not sales:
        flash("No sales data available for the selected date", "info")
        return render_template('daily_sales_report.html', 
                               sales=[], 
                               today=report_date, 
                               total_sales=0, 
                               total_transactions=0, 
                               daily_profit=0, 
                               mpesa_total=0,  # Include M-Pesa total
                               credit_total=0,  # Include credit total
                               most_sold_item=None, 
                               most_sold_quantity=0)

    # Calculate sales data including M-Pesa and credit totals
    total_sales = sum(sale.total for sale in sales)
    total_transactions = len(sales)
    daily_profit = sum(sale.profit for sale in sales)
    
    # Totals based on payment methods
    mpesa_total = sum(sale.total for sale in sales if sale.payment_method.lower() == 'mpesa')
    credit_total = sum(sale.total for sale in sales if sale.payment_method.lower() == 'credit')

    # Track quantity sold for each item
    item_sales = Counter()
    for sale in sales:
        for item in sale.cart_items:
            item_sales[item.product.name] += item.quantity

    most_sold_item, most_sold_quantity = max(item_sales.items(), key=lambda x: x[1], default=(None, 0))

    return render_template('daily_sales_report.html', 
                           sales=sales, 
                           today=report_date, 
                           total_sales=round(total_sales, 2), 
                           total_transactions=total_transactions, 
                           daily_profit=round(daily_profit, 2), 
                           mpesa_total=round(mpesa_total, 2),  # Include M-Pesa total
                           credit_total=round(credit_total, 2),  # Include credit total
                           most_sold_item=most_sold_item, 
                           most_sold_quantity=most_sold_quantity)
@sales_bp.route('/reports/filter', methods=['GET'])
@login_required
def filter_sales_report():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if not start_date_str or not end_date_str:
        flash("Please provide both start and end dates", "warning")
        return redirect(url_for('sales.daily_sales_report'))

    # Parse dates with error handling
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        if start_date > end_date:
            flash("Start date must be before or equal to end date.", "warning")
            return redirect(url_for('sales.daily_sales_report'))
    except ValueError:
        flash("Invalid date format. Please use YYYY-MM-DD.", "danger")
        return redirect(url_for('sales.daily_sales_report'))

    # Fetch sales within the specified date range
    sales = Sale.query.filter(Sale.date >= start_date, Sale.date <= end_date).all()

    if not sales:
        flash("No sales data available for the selected date range", "info")
        return render_template('filtered_sales_report.html', 
                               sales=[], 
                               total_sales=0, 
                               total_transactions=0, 
                               total_profit=0, 
                               avg_sale_value=0, 
                               unique_products=0, 
                               most_sold_item=None, 
                               most_sold_quantity=0,
                               mpesa_total=0,
                               credit_total=0)

    # Calculate total sales, transactions, and total profit
    total_sales = sum(sale.total for sale in sales)
    total_transactions = len(sales)
    total_profit = sum(sale.profit for sale in sales)

    # Track quantity sold for each item
    item_sales = Counter()
    for sale in sales:
        for item in sale.cart_items:
            item_sales[item.product.name] += item.quantity

    # Determine the most sold item based on quantities
    most_sold_item, most_sold_quantity = max(item_sales.items(), key=lambda x: x[1], default=(None, 0))

    # Calculate average sale value and unique products
    avg_sale_value = total_sales / total_transactions if total_transactions else 0
    unique_products = len(set(item.product.name for sale in sales for item in sale.cart_items))

    # Calculate totals based on payment methods
    mpesa_total = sum(sale.total for sale in sales if sale.payment_method.lower() == 'mpesa')
    credit_total = sum(sale.total for sale in sales if sale.payment_method.lower() == 'credit')

    return render_template('filtered_sales_report.html', 
                           sales=sales, 
                           total_sales=round(total_sales, 2), 
                           total_transactions=total_transactions, 
                           total_profit=round(total_profit, 2), 
                           avg_sale_value=round(avg_sale_value, 2), 
                           unique_products=unique_products, 
                           most_sold_item=most_sold_item, 
                           most_sold_quantity=most_sold_quantity,
                           mpesa_total=round(mpesa_total, 2),  # Include M-Pesa total
                           credit_total=round(credit_total, 2))  # Include credit total

@sales_bp.route('/reports/monthly', methods=['GET'])
@login_required
def monthly_sales_report():
    month_str = request.args.get('month', datetime.today().strftime('%Y-%m'))
    try:
        report_month = datetime.strptime(month_str, '%Y-%m').date()
    except ValueError:
        flash("Invalid month format. Please use YYYY-MM.", "danger")
        return redirect(url_for('sales_bp.monthly_sales_report'))

    # Fetch sales for the specified month
    sales = Sale.query.filter(func.extract('year', Sale.date) == report_month.year,
                               func.extract('month', Sale.date) == report_month.month).all()

    # Calculate total sales, transactions, and profit
    total_sales = sum(sale.total for sale in sales)
    total_transactions = len(sales)
    total_profit = sum(sale.profit for sale in sales)

    # Render the report template with calculated values and the datetime module
    return render_template('monthly_sales_report.html', 
                           sales=sales, 
                           total_sales=round(total_sales, 2), 
                           total_transactions=total_transactions, 
                           total_profit=round(total_profit, 2),
                           datetime=datetime) 
