from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import db, Product, Category, Supplier, Expense ,AdjustmentType, StockLog, User 
from app import socketio
from decimal import Decimal, InvalidOperation
from sqlalchemy.exc import IntegrityError

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
stock_bp = Blueprint('stock', __name__)

MAX_STOCK_LIMIT = 1000

# Constants for flash messages
FLASH_ACCESS_DENIED = 'Access denied.'
FLASH_CATEGORY_EXISTS = 'Category already exists.'
FLASH_PRODUCT_EXISTS = 'Product already exists.'
FLASH_CATEGORY_CREATED = 'Category "{}" created successfully.'
FLASH_CATEGORY_UPDATED = 'Category "{}" updated successfully.'
FLASH_CATEGORY_DELETED = 'Category "{}" deleted successfully.'
FLASH_PRODUCT_ADDED = 'Product "{}" added successfully.'
FLASH_PRODUCT_UPDATED = 'Product "{}" updated successfully.'
FLASH_PRODUCT_DELETED = 'Product "{}" deleted successfully.'
FLASH_INSUFFICIENT_STOCK = 'Insufficient stock for {}.'
FLASH_STOCK_UPDATED = 'Stock for "{}" updated successfully.'

# Route to manage product categories
@stock_bp.route('/categories')
@login_required
def categories():
    categories = Category.query.all()
    if not categories:
        flash('No categories found.', 'info')
    return render_template('categories.html', categories=categories)


# Route to create a new category
@stock_bp.route('/categories/new', methods=['GET', 'POST'])
@login_required
def new_category():
    if not current_user.is_admin():
        flash(FLASH_ACCESS_DENIED)
        return redirect(url_for('stock.categories'))

    if request.method == 'POST':
        name = request.form.get('name').strip()
        if not name:
            flash("Category name cannot be empty.", "danger")
            return redirect(url_for('stock.new_category'))

        if Category.query.filter_by(name=name).first():
            flash(FLASH_CATEGORY_EXISTS)
            return redirect(url_for('stock.new_category'))

        new_category = Category(name=name)
        db.session.add(new_category)
        db.session.commit()
        flash(FLASH_CATEGORY_CREATED.format(name))
        return redirect(url_for('stock.categories'))

    return render_template('new_category.html')


# Route to edit an existing category
@stock_bp.route('/categories/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_category(id: int):
    category = Category.query.get_or_404(id)

    if request.method == 'POST':
        new_name = request.form['name'].strip()
        if not new_name:
            flash("Category name cannot be empty.", "danger")
            return redirect(url_for('stock.edit_category', id=id))

        if Category.query.filter_by(name=new_name).first():
            flash("Category with this name already exists.", "danger")
            return redirect(url_for('stock.edit_category', id=id))

        category.name = new_name
        db.session.commit()
        flash(FLASH_CATEGORY_UPDATED.format(category.name))
        return redirect(url_for('stock.categories'))

    return render_template('edit_category.html', category=category)


# Route to delete a category
@stock_bp.route('/categories/<int:id>/delete', methods=['POST'])
@login_required
def delete_category(id: int):
    category = Category.query.get_or_404(id)
    try:
        db.session.delete(category)
        db.session.commit()
        flash(FLASH_CATEGORY_DELETED.format(category.name))
    except Exception as e:
        db.session.rollback()
        flash(f"An error occurred while deleting the category: {str(e)}", "danger")
    return redirect(url_for('stock.categories'))

@stock_bp.route('/products', methods=['GET'])
@login_required
def products():
    # Get the search query from the URL parameters
    search_query = request.args.get('search', '')

    # Query the database without pagination
    products_query = Product.query.filter(Product.name.contains(search_query))
    
    # Get all products
    products = products_query.all()

    # Render the template with all products
    if current_user.is_admin():
        return render_template('products.html', products=products, search_query=search_query)
    elif current_user.is_cashier():
        return render_template('cashier_products_view.html', products=products, search_query=search_query)
    else:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('home.index'))  # Redirect to a safe place if the user role is not recognized

@stock_bp.route('/products/new', methods=['GET', 'POST'])
@login_required
def new_product():
    if not current_user.is_admin():
        flash(FLASH_ACCESS_DENIED)
        return redirect(url_for('stock.products'))

    categories = Category.query.all()
    suppliers = Supplier.query.all()

    if request.method == 'POST':
        product_data = {
            'name': request.form['name'].strip(),
            'cost_price': request.form['cost_price'].strip(),
            'selling_price': request.form['selling_price'].strip(),
            'stock': request.form['stock'].strip(),
            'category_id': request.form['category'],
            'supplier_id': request.form.get('supplier'),
            'combination_size': request.form.get('combination_size', '').strip(),
            'combination_price': request.form.get('combination_price', '').strip()
        }

        # Validate and create the product
        validation_error = validate_product_data(product_data)
        if validation_error:
            flash(validation_error)
            return redirect(url_for('stock.new_product'))

        new_product = create_product(product_data)
        db.session.add(new_product)
        db.session.commit()
        flash(FLASH_PRODUCT_ADDED.format(new_product.name))

        # Emit socket update
        socketio.emit('stock_updated', {
            'id': new_product.id,
            'name': new_product.name,
            'stock': new_product.stock
        }, broadcast=True)

        return redirect(url_for('stock.products'))

    return render_template('new_product.html', categories=categories, suppliers=suppliers)

def validate_product_data(data):
    # Check if the product already exists
    if Product.query.filter_by(name=data['name']).first():
        return FLASH_PRODUCT_EXISTS

    # Check required fields
    required_fields = [data['name'], data['cost_price'], data['selling_price'], data['stock'], data['category_id']]
    for field, value in zip(['Name', 'Cost Price', 'Selling Price', 'Stock', 'Category'], required_fields):
        if not value:
            return f"{field} is required."

    # Validate numeric fields
    try:
        data['cost_price'] = Decimal(data['cost_price'])
        data['selling_price'] = Decimal(data['selling_price'])
        data['stock'] = int(data['stock'])
        if data['cost_price'] <= 0 or data['selling_price'] <= 0 or data['stock'] < 0:
            return "Cost price, selling price, and stock must be positive numbers."
    except (ValueError, InvalidOperation):
        return "Cost price, selling price, and stock must be valid numbers."

    # Validate combination fields if provided
    if data['combination_size'] and data['combination_price']:
        try:
            data['combination_size'] = int(data['combination_size'])
            data['combination_price'] = Decimal(data['combination_price'])
            if data['combination_size'] <= 0 or data['combination_price'] <= 0:
                return "Combination size and price must be positive numbers."
        except (ValueError, InvalidOperation):
            return "Combination size and price must be valid positive numbers."

    return None  # No errors


def create_product(data):
    combination_unit_price = None
    if data['combination_size'] and data['combination_price']:
        combination_unit_price = float(data['combination_price']) / int(data['combination_size'])

    return Product(
        name=data['name'],
        cost_price=float(data['cost_price']),
        selling_price=float(data['selling_price']),
        stock=float(data['stock']),
        category_id=data['category_id'],
        supplier_id=data['supplier_id'],
        combination_size=int(data['combination_size']) if data['combination_size'] else None,
        combination_price=float(data['combination_price']) if data['combination_price'] else None,
        combination_unit_price=combination_unit_price
    )




@stock_bp.route('/products/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_product(id: int):
    if not current_user.is_admin():
        flash("Access denied.", "danger")
        return redirect(url_for('stock.products'))

    product = Product.query.get_or_404(id)
    categories = Category.query.all()

    if request.method == 'POST':
        try:
            # Retrieve and validate input fields
            name = request.form['name']
            selling_price = float(request.form['selling_price'])

            # Update product data
            product.name = name
            product.selling_price = selling_price
            product.category_id = request.form['category']

            db.session.commit()
            flash(f"Product '{product.name}' updated successfully.", "success")

            # Emit real-time update for product change
            socketio.emit('product_updated', {
                'id': product.id,
                'name': product.name,
                'selling_price': product.selling_price
            }, broadcast=True)

            return redirect(url_for('stock.products'))

        except Exception as e:
            db.session.rollback()
            flash(f"An error occurred while updating the product: {str(e)}", "danger")
            return redirect(url_for('stock.edit_product', id=id))

    return render_template('edit_product.html', product=product, categories=categories)


@stock_bp.route('/products/<int:id>/delete', methods=['POST'])
@login_required
def delete_product(id: int):
    if not current_user.is_admin():
        flash(FLASH_ACCESS_DENIED)
        return redirect(url_for('stock.products'))

    product = Product.query.get_or_404(id)

    try:
        db.session.delete(product)
        db.session.commit()
        flash(FLASH_PRODUCT_DELETED.format(product.name), 'success')

        # Emit real-time stock update (stock set to 0)
        socketio.emit('stock_updated', {
            'id': product.id,
            'name': product.name,
            'stock': 0
        }, broadcast=True)

    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the product. Please try again.', 'danger')



def update_product_stock(product, quantity_to_add, total_amount):
    """Helper function to update product stock and log expenses."""
    # Ensure quantity_to_add is valid
    if quantity_to_add <= 0:
        raise ValueError("Quantity to add must be positive.")

    # Update the stock with the quantity being added
    product.stock += quantity_to_add

    # Update cost price if quantity added is greater than 0
    if quantity_to_add > 0:
        new_cost_price = total_amount / quantity_to_add
        product.cost_price = new_cost_price  # Update cost price in the product

    # Log the stock addition as an expense
    new_expense = Expense(
        description=f"Stock added for {product.name}",
        amount=total_amount,
        category="Stock Update",
        quantity=quantity_to_add  # Optional: Include quantity in the expense
    )
    db.session.add(new_expense)

# Route to display the product management page
@stock_bp.route('/admin_update_stock', methods=['GET'])
@login_required
def update_stock_page():
    products = Product.query.all()
    return render_template('update_stock.html', products=products)

@stock_bp.route('/products/<int:product_id>/update_stock', methods=['POST'])
@login_required
def update_stock(product_id):
    product = Product.query.get_or_404(product_id)

    quantity = request.form.get('quantity')
    
    if quantity is None:
        return jsonify({'message': 'Quantity is required'}), 400
    
    try:
        quantity = int(quantity)
    except ValueError:
        return jsonify({'message': 'Quantity must be a number'}), 400

    if quantity < 0:
        return jsonify({'message': 'Quantity cannot be negative'}), 400

    try:
        product.stock += quantity

        # Optional: Check for max stock limit
        if product.stock > MAX_STOCK_LIMIT:
            return jsonify({'message': 'Stock cannot exceed maximum limit'}), 400

        db.session.commit()

        # Log the update
        logger.info(f'User {current_user.id} updated stock for product {product_id} by {quantity}. New stock: {product.stock}')

        return jsonify({
            'message': 'Stock updated successfully',
            'new_stock': product.stock,
            'product_id': product.id,
            'product_name': product.name  # Assuming you have a name attribute
        }), 200
    except IntegrityError:
        db.session.rollback()
        return jsonify({'message': 'Error updating stock due to database integrity issues'}), 500
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': f'An unexpected error occurred: {str(e)}'}), 500
@stock_bp.route('/products/<int:product_id>/update_selling_price', methods=['POST'])
@login_required
def update_selling_price(product_id):
    product = Product.query.get_or_404(product_id)

    # Get the form data
    new_selling_price = request.form.get('selling_price', type=float)
    combination_size = request.form.get('combination_size', type=int)
    combination_price = request.form.get('combination_price', type=float)

    # Validate inputs
    if new_selling_price is None and (combination_size is None or combination_price is None):
        return jsonify({'message': 'Invalid selling price or combination values'}), 400
    if new_selling_price is not None and new_selling_price < 0:
        return jsonify({'message': 'Invalid selling price value'}), 400
    if combination_size is not None and combination_price is not None:
        if combination_size <= 0 or combination_price <= 0:
            return jsonify({'message': 'Combination size and price must be positive values'}), 400

    try:
        # Update the selling price directly
        if new_selling_price is not None:
            product.selling_price = new_selling_price
        
        # Update combination details if provided
        if combination_size is not None and combination_price is not None:
            product.combination_size = combination_size
            product.combination_price = combination_price
            product.combination_unit_price = combination_price / combination_size if combination_size > 0 else None

        # Commit the changes to the database
        db.session.commit()

        return jsonify({
            'message': 'Selling price updated successfully',
            'selling_price': str(product.selling_price),
            'combination_size': product.combination_size,
            'combination_price': str(product.combination_price),
            'combination_unit_price': str(product.combination_unit_price) if product.combination_unit_price is not None else None
        }), 200
    except IntegrityError:
        db.session.rollback()
        return jsonify({'message': 'Error updating selling price'}), 500
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': f'An unexpected error occurred: {str(e)}'}), 500

# Route to update cost price
@stock_bp.route('/products/<int:product_id>/update_cost_price', methods=['POST'])
@login_required
def update_cost_price(product_id):
    product = Product.query.get_or_404(product_id)
    new_cost_price = request.form.get('cost_price', type=float)

    if new_cost_price is None or new_cost_price < 0:
        return jsonify({'message': 'Invalid cost price value'}), 400

    try:
        product.cost_price = new_cost_price
        db.session.commit()
        return jsonify({
            'message': 'Cost price updated successfully',
            'cost_price': str(product.cost_price)
        }), 200
    except IntegrityError:
        db.session.rollback()
        return jsonify({'message': 'Error updating cost price'}), 500
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': f'An unexpected error occurred: {str(e)}'}), 500




@stock_bp.route('/products/<int:product_id>/update_stock_modal', methods=['GET'])
@login_required
def update_stock_modal(product_id: int):
    product = Product.query.get_or_404(product_id)
    return render_template('update_stock_modal.html', product=product)

from sqlalchemy.exc import SQLAlchemyError

@stock_bp.route('/products/<int:product_id>/update_stock', methods=['POST'])
@login_required
def update_stock_product(product_id: int):
    product = Product.query.get_or_404(product_id)
    quantity_to_add = int(request.form['quantity'])
    total_amount = float(request.form['total_amount'])

    # Validate input
    if quantity_to_add <= 0:
        return jsonify({'message': "Quantity must be a positive integer."}), 400
    if total_amount < 0:
        return jsonify({'message': "Total amount cannot be negative."}), 400

    try:
        update_product_stock(product, quantity_to_add, total_amount)
        db.session.commit()
        socketio.emit('stock_updated', {
            'id': product.id,
            'name': product.name,
            'stock': product.stock,
            'cost_price': product.cost_price
        }, broadcast=True)
        return jsonify({'message': f"Stock updated successfully for {product.name}."}), 200

    except ValueError as ve:
        db.session.rollback()
        return jsonify({'message': str(ve)}), 400  # Return specific validation error
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({'message': 'Database error. Please try again.'}), 500
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@stock_bp.route('/api/low-stock-products', methods=['GET'])
def get_low_stock_products():
    low_stock_products = Product.query.filter(Product.stock < 5).all()  # Fetch products with stock less than 5
    low_stock_count = len(low_stock_products)

    # Construct a list of product details to return
    products_data = [
        {
            'id': product.id,
            'name': product.name,
            'stock': product.stock,
            'cost_price': product.cost_price,  
            'selling_price': product.selling_price  # Include selling price
        }
        for product in low_stock_products
    ]

    return jsonify({
        'low_stock_count': low_stock_count,
        'products': products_data  # Return detailed product data
    })

@stock_bp.route('/adjust-stock/<int:product_id>', methods=['GET', 'POST'])
@login_required
def adjust_stock(product_id):
    product = Product.query.get_or_404(product_id)
    
    # Check user roles
    is_admin = current_user.is_admin()
    is_cashier = current_user.is_cashier()

    if request.method == 'POST':
        try:
            # Retrieve data from form
            adjustment_quantity = int(request.form['adjustment_quantity'])
            change_reason = request.form.get('change_reason', '').strip()  # Change reason is optional
            adjustment_type = request.form.get('adjustment_type')

            # Validate adjustment quantity
            if adjustment_quantity < 1:
                flash('Adjustment quantity must be greater than zero.', 'danger')
                logger.warning(f'Invalid quantity {adjustment_quantity} attempted by user {current_user.id} on product {product.id}')
                return redirect(url_for('stock.product_detail', product_id=product.id))

            # Validate change reason if provided
            if change_reason and len(change_reason) < 5:
                flash('If provided, change reason must be at least 5 characters long.', 'danger')
                logger.warning(f'Insufficient reason length by user {current_user.id} on product {product.id}')
                return redirect(url_for('stock.product_detail', product_id=product.id))

            # Determine allowed adjustment types based on user role
            allowed_types = ['addition', 'reduction', 'returned'] if is_cashier else [e.value for e in AdjustmentType]
            
            # Validate the adjustment type
            if adjustment_type not in allowed_types:
                flash('Unauthorized adjustment type for your role.', 'danger')
                logger.warning(f'Unauthorized adjustment attempt by user {current_user.id} on product {product.id}: {adjustment_type}')
                return redirect(url_for('stock.product_detail', product_id=product.id))

            # Calculate the new stock level based on the adjustment type
            if adjustment_type == 'addition':
                new_stock = product.stock + adjustment_quantity
            elif adjustment_type == 'reduction':
                new_stock = max(product.stock - adjustment_quantity, 0)  # Ensures stock can't go negative
            elif adjustment_type == 'returned':
                new_stock = product.stock + adjustment_quantity  # Increase stock for returned items
            elif adjustment_type in ['spoilage', 'damage', 'theft']:
                new_stock = max(product.stock - adjustment_quantity, 0)  # Decrease stock for spoilage, damage, or theft
            elif adjustment_type == 'inventory_adjustment':
                new_stock = adjustment_quantity  # Set stock to the provided amount
            else:
                flash('Invalid adjustment type.', 'danger')
                logger.warning(f'Invalid adjustment type {adjustment_type} attempted by user {current_user.id} on product {product.id}')
                return redirect(url_for('stock.product_detail', product_id=product.id))

            # Log the stock update
            stock_log = StockLog(
                product_id=product.id,
                user_id=current_user.id,
                previous_stock=product.stock,
                new_stock=new_stock,
                adjustment_type=adjustment_type,
                change_reason=change_reason or None  
            )
            
            # Update the product's stock in the database
            product.stock = new_stock
            
            db.session.add(stock_log)
            db.session.commit()
            
            flash(f'Stock for {product.name} updated successfully.', 'success')
            logger.info(f'Stock for {product.name} updated from {product.stock} to {new_stock} by user {current_user.id} with adjustment type {adjustment_type}')
            return redirect(url_for('stock.products'))

        except ValueError as ve:
            flash('Invalid input for quantity. Please enter a valid number.', 'danger')
            logger.error(f'ValueError: {str(ve)} by user {current_user.id} on product {product.id}')
        except SQLAlchemyError as e:
            db.session.rollback()  # Rollback in case of database errors
            flash('An error occurred while updating stock. Please try again.', 'danger')
            logger.error(f'Database error: {str(e)} by user {current_user.id} on product {product.id}')
        except Exception as e:
            flash('An unexpected error occurred. Please try again.', 'danger')
            logger.error(f'Unexpected error: {str(e)} by user {current_user.id} on product {product.id}')

    # Render the appropriate template based on user role
    template_name = 'adjust_stock_cashier.html' if is_cashier else 'adjust_stock_admin.html'
    allowed_types = ['addition', 'return'] if is_cashier else [e.value for e in AdjustmentType]
    
    return render_template(template_name, product=product, allowed_types=allowed_types)


@stock_bp.route('/stock-logs', methods=['GET'])
@login_required
def stock_logs():
    # Fetch all stock logs ordered by date, most recent first
    logs = StockLog.query.order_by(StockLog.date.desc()).all()
    
    # Render the template and pass the logs
    return render_template('stock_logs.html', logs=logs)

@stock_bp.route('/api/stock-logs', methods=['GET'])
@login_required
def get_stock_logs():
    try:
        # Fetch all stock logs from the database, joining with Product and User to get their names
        stock_logs = db.session.query(
            StockLog,
            Product.name.label('product_name'),  # Get the product name
            User.username.label('user_name')      # Get the user name
        ).join(Product).join(User).all()

        # Convert stock logs to a list of dictionaries
        stock_logs_data = [{
            'id': log.id,
            'product_name': log.product_name,    # Use product_name from the query
            'user_name': log.user_name,          # Use user_name from the query
            'date': log.date.isoformat(),        # Convert datetime to string
            'previous_stock': log.previous_stock,
            'new_stock': log.new_stock,
            'adjustment_type': log.adjustment_type.value
            
        } for log, log.product_name, log.user_name in stock_logs]  # Unpacking the query results

        return jsonify({'stock_logs': stock_logs_data}), 200

    except Exception as e:
        # Handle any unexpected errors
        return jsonify({'message': 'An error occurred while fetching stock logs: ' + str(e)}), 500
