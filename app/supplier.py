from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required
from app import  db
from app.models import Supplier, Product
import logging

supplier_bp = Blueprint('supplier', __name__)

@supplier_bp.route('/suppliers', methods=['GET'])
@login_required
def suppliers_page():
    products = Product.query.all()  # Fetch all products
    return render_template('suppliers.html', products=products)  # Pass products to the template

@supplier_bp.route('/api/suppliers', methods=['GET'])
@login_required
def get_suppliers():
    try:
        suppliers = Supplier.query.all()
        return jsonify([supplier.serialize() for supplier in suppliers]), 200
    except Exception as e:
        logging.error(f"Error fetching suppliers: {e}")
        return jsonify({'error': 'Failed to fetch suppliers.'}), 500


@supplier_bp.route('/api/add_supplier', methods=['POST'])
@login_required
def add_supplier():
    try:
        data = request.get_json()
        name = data.get('name')
        phone = data.get('phone')
        product_id = data.get('product_id')  # Add this if you need to associate supplier with a product

        if not name:
            return jsonify({'error': 'Supplier name is required.'}), 400

        # Check if the supplier already exists
        existing_supplier = Supplier.query.filter_by(name=name).first()
        if existing_supplier:
            return jsonify({'error': 'Supplier with this name already exists.'}), 400

        new_supplier = Supplier(
            name=name,
            phone=phone
        )
        
        db.session.add(new_supplier)
        db.session.commit()

        # Optionally associate the supplier with a product if needed
        if product_id:
            product = Product.query.get(product_id)
            if product:
                product.supplier = new_supplier  # Assuming a one-to-one relationship

        return jsonify({'message': 'Supplier added successfully.'}), 200

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error adding supplier: {e}")  # Log the error for debugging
        return jsonify({'error': 'Failed to add supplier. Please try again.'}), 500
