from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user
from app import db, admin_required
from app.models import Expense
import logging
from datetime import datetime

expense_bp = Blueprint('expense', __name__)


@expense_bp.route('/expenses')
@login_required
def expenses_page():
    return render_template('expenses.html')  # Create this template


@expense_bp.route('/api/expenses', methods=['GET'])
@login_required
def get_expenses():
    date_filter = request.args.get('date')
    query = Expense.query

    if date_filter:
        # Assuming date_filter is in the format YYYY-MM-DD
        query = query.filter(Expense.date >= f"{date_filter} 00:00:00", 
                             Expense.date <= f"{date_filter} 23:59:59")
    
    expenses = query.all()
    return jsonify([{
        'id': expense.id,
        'description': expense.description,
        'amount': expense.amount,
        'date': expense.date.strftime("%Y-%m-%d %H:%M:%S"),
        'category': expense.category
    } for expense in expenses])

@expense_bp.route('/api/add_daily_expense', methods=['POST'])
@login_required
def add_daily_expense():
    try:
        data = request.get_json()
        description = data.get('description', '').strip()
        amount = data.get('amount')

        # Validate input
        if not description or not isinstance(amount, (float, int)) or float(amount) <= 0 or len(description) > 255:
            logging.error("Invalid input data")
            return jsonify({'error': 'Invalid input data'}), 400

        # Create new expense
        new_expense = Expense(
            description=description,
            amount=float(amount),
            category="Daily Expenses",
            date=datetime.now(),
        )
        db.session.add(new_expense)
        db.session.commit()
        logging.info(f"Expense added successfully by user {current_user.id}.")

        return jsonify({
            'message': 'Daily expense added successfully.',
            'expense_id': new_expense.id
        }), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        logging.error(f"Database error: {e}")
        return jsonify({'error': 'Failed to add expense due to database error.'}), 500
    except Exception as e:
        db.session.rollback()
        logging.error(f"Unexpected error: {e}")
        return jsonify({'error': 'Failed to add daily expense. Please try again.'}), 500


@expense_bp.route('/api/total_daily_expenditure', methods=['GET'])
@login_required
def total_daily_expenditure():
    """Fetch total daily expenditure with an optional date filter."""
    date_filter = request.args.get('date')
    
    try:
        if date_filter:
            # Validate and parse the date filter
            parsed_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
            expenses = Expense.query.filter(Expense.date >= f"{parsed_date} 00:00:00",
                                             Expense.date <= f"{parsed_date} 23:59:59").all()
        else:
            # If no date is provided, fetch today's expenses
            today = datetime.now().date()
            expenses = Expense.query.filter(Expense.date >= f"{today} 00:00:00",
                                             Expense.date <= f"{today} 23:59:59").all()

        # Calculate the total expenditure
        total_expenditure = sum(expense.amount for expense in expenses)

        # Prepare the response
        response_data = {
            'success': True,
            'total_expenditure': total_expenditure,
            'date': date_filter if date_filter else today.strftime("%Y-%m-%d"),
            'expenses': [{
                'id': expense.id,
                'description': expense.description,
                'amount': expense.amount,
                'date': expense.date.strftime("%Y-%m-%d %H:%M:%S"),
                'category': expense.category
            } for expense in expenses]
        }

        return jsonify(response_data), 200

    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Failed to fetch total daily expenditure. Please try again.'}), 500 




@expense_bp.route('/expenses_report', methods=['GET'])
@login_required
def render_expenses_report():
    """Render the Expenses Report page."""
    return render_template('expenses_report.html')



@expense_bp.route('/api/expenses_report', methods=['GET'])
@login_required
def expenses_report():
    """Fetch expenses within a specified date range."""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # Set default to today's date if no dates are provided
    if not start_date or not end_date:
        today = datetime.today().date()
        start_date = today.strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

    try:
        query = Expense.query
        
        # Parse the dates
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

        # Filter by date range
        query = query.filter(Expense.date >= f"{start_date} 00:00:00",
                             Expense.date <= f"{end_date} 23:59:59")

        expenses = query.order_by(Expense.date.desc()).all()
        
        # Calculate total expenditures and differentiate categories
        total_expenditure = float(sum(exp.amount for exp in expenses))
        total_stock_expenditure = float(sum(exp.amount for exp in expenses if exp.category == 'Stock Update'))
        total_daily_expenditure = float(sum(exp.amount for exp in expenses if exp.category == 'Daily Expenses'))

        response_data = {
            'success': True,
            'total_expenditure': total_expenditure,
            'total_stock_expenditure': total_stock_expenditure,
            'total_daily_expenditure': total_daily_expenditure,
            'expenses': [{
                'id': exp.id,
                'description': exp.description,
                'amount': float(exp.amount),
                'date': exp.date.strftime("%Y-%m-%d %H:%M:%S"),
                'category': exp.category or 'Daily Expenses'
            } for exp in expenses]
        }
        return jsonify(response_data), 200

    except Exception as e:
        print(f"Error fetching expenses report: {e}")  # More descriptive error message for debugging
        return jsonify({'success': False, 'error': 'Failed to fetch expenses report.'}), 500



@expense_bp.route('/api/todays_expenditure', methods=['GET'])
@login_required
def todays_expenditure():
    """Fetch today's total expenditure."""
    try:
        today = datetime.now().date()
        start_of_day = datetime.combine(today, datetime.min.time())
        end_of_day = datetime.combine(today, datetime.max.time())

        expenses = Expense.query.filter(
            Expense.date >= start_of_day,
            Expense.date <= end_of_day
        ).all()

        # Cast total_expenditure to float to ensure it's numeric
        total_expenditure = float(sum(exp.amount for exp in expenses))
        return jsonify({
            'success': True,
            'total_expenditure': total_expenditure
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'error': 'Failed to fetch today\'s expenditure.'}), 500
