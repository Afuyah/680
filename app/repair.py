from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError
from app.models import RepairService, User, RepairStatus, PaymentStatus
import logging
from datetime import datetime
from app import db
# Initialize repair blueprint and logger
repair_bp = Blueprint('repair', __name__)
logger = logging.getLogger(__name__)

@repair_bp.route('/repairs', methods=['GET'])
@login_required
def list_repairs():
    """List all repairs with filters for status."""
    logger.info(f"User {current_user.username} accessed repair list.")
    status_filter = request.args.get('status', 'active')

    try:
        query = RepairService.query
        
        # Apply filters based on the status parameter
        if status_filter == 'pending':
            query = query.filter(RepairService.progress_status == RepairStatus.PENDING)
        elif status_filter == 'completed':
            query = query.filter(RepairService.progress_status == RepairStatus.COMPLETED)
        else:  # Default to showing only active (non-completed) jobs
            query = query.filter(RepairService.progress_status != RepairStatus.COMPLETED)
        
        repairs = query.all()
        return render_template('repair/repairs.html', repairs=repairs, status_filter=status_filter)
    except SQLAlchemyError as e:
        logger.error(f"Error accessing repair list: {e}")
        flash('Error loading repairs. Please try again later.', 'danger')
        return render_template('repair/repairs.html', repairs=[], status_filter=status_filter)


@repair_bp.route('/view_repair/<int:repair_id>', methods=['GET'])
@login_required
def view_repair(repair_id):
    """View repair details."""
    try:
        repair = RepairService.query.get_or_404(repair_id)
        logger.info(f"User {current_user.username} viewed repair {repair.reference_number}.")
        return render_template('repair/view_repair.html', repair=repair)
    except SQLAlchemyError as e:
        logger.error(f"Error viewing repair {repair_id}: {e}")
        flash('Error loading repair details. Please try again later.', 'danger')
        return redirect(url_for('repair.list_repairs'))

@repair_bp.route('/add_repair', methods=['GET', 'POST'])
@login_required
def add_repair():
    """Add a new repair entry."""
    if request.method == 'POST':
        try:
            # Extract and validate form data
            customer_name = request.form['customer_name']
            item_model = request.form['item_model']
            service_type = request.form['service_type']
            amount = float(request.form['amount'])
            # Auto-generate reference number or accept from form data
            reference_number = RepairService.create_reference_number()  # Auto-generate reference number
            expected_collection_date = datetime.strptime(request.form['expected_collection_date'], '%Y-%m-%d')
            added_by_user_id = current_user.id

            # Check for duplicate reference number
            if RepairService.query.filter_by(reference_number=reference_number).first():
                flash('Reference number already exists.', 'danger')
                return redirect(url_for('repair.add_repair'))

            # Create new repair entry with enum values for progress and payment status
            new_repair = RepairService(
                customer_name=customer_name,
                item_model=item_model,
                service_type=service_type,
                amount_due=amount,
                progress_status=RepairStatus.PENDING, 
                payment_status=PaymentStatus.UNPAID, 
                reference_number=reference_number,
                expected_collection_date=expected_collection_date,
                added_by_user_id=added_by_user_id
            )

            # Add new repair to database
            db.session.add(new_repair)
            db.session.commit()

            logger.info(f"User {current_user.username} added new repair with reference {reference_number}.")
            flash('Repair added successfully!', 'success')
            return redirect(url_for('repair.list_repairs'))

        except ValueError:
            flash('Invalid data format. Please check your entries.', 'danger')
            logger.warning("Invalid input data format during repair addition.")
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Database error while adding repair: {e}")
            flash('Database error. Could not add repair.', 'danger')

    return render_template('repair/add_repair.html')


@repair_bp.route('/edit_repair/<int:repair_id>', methods=['GET', 'POST'])
@login_required
def edit_repair(repair_id):
    """Edit existing repair details."""
    repair = Repair.query.get_or_404(repair_id)
    if request.method == 'POST':
        try:
            repair.customer_name = request.form['customer_name']
            repair.item_model = request.form['item_model']
            repair.service_type = request.form['service_type']
            repair.amount = float(request.form['amount'])
            repair.expected_collection_date = datetime.strptime(request.form['expected_collection_date'], '%Y-%m-%d')
            repair.progress_status = request.form['progress_status']
            repair.payment_status = request.form['payment_status']
            db.session.commit()

            logger.info(f"User {current_user.username} updated repair {repair.reference_number}.")
            flash('Repair updated successfully!', 'success')
            return redirect(url_for('repair.list_repairs'))

        except ValueError:
            flash('Invalid data format. Please check your entries.', 'danger')
            logger.warning(f"Invalid data format during edit for repair {repair.reference_number}.")
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Database error while editing repair {repair.reference_number}: {e}")
            flash('Database error. Could not update repair.', 'danger')

    return render_template('repair/edit_repair.html', repair=repair)

@repair_bp.route('/delete_repair/<int:repair_id>', methods=['POST'])
@login_required
def delete_repair(repair_id):
    """Delete a repair entry."""
    try:
        repair = Repair.query.get_or_404(repair_id)
        db.session.delete(repair)
        db.session.commit()

        logger.info(f"User {current_user.username} deleted repair {repair.reference_number}.")
        flash('Repair deleted successfully.', 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Error deleting repair {repair_id}: {e}")
        flash('Database error. Could not delete repair.', 'danger')

    return redirect(url_for('repair.list_repairs'))

@repair_bp.route('/update_status/<int:repair_id>', methods=['GET', 'POST'])
@login_required
def update_status(repair_id):
    """Render the update status page for a repair entry."""
    try:
        repair = RepairService.query.get_or_404(repair_id)

        if request.method == 'POST':
            try:
                new_status = request.form['progress_status']
                new_status_enum = RepairStatus[new_status.replace(" ", "_").upper()]  # Convert to enum
                
                # Prevent going back on status (status cannot go back)
                if repair.progress_status == RepairStatus.COMPLETED and new_status_enum != RepairStatus.COMPLETED:
                    flash("You cannot change the status once the repair is completed.", 'danger')
                    return redirect(url_for('repair.view_repair', repair_id=repair_id))

                if repair.progress_status == RepairStatus.IN_PROGRESS and new_status_enum == RepairStatus.PENDING:
                    flash("You cannot revert the status from 'In Progress' to 'Pending'.", 'danger')
                    return redirect(url_for('repair.view_repair', repair_id=repair_id))

                if repair.progress_status == RepairStatus.PENDING and new_status_enum == RepairStatus.COMPLETED:
                    flash("You cannot mark the repair as 'Completed' directly from 'Pending'.", 'danger')
                    return redirect(url_for('repair.view_repair', repair_id=repair_id))

                if repair.payment_status != 'Paid' and new_status_enum == RepairStatus.COMPLETED:
                    flash("The repair must be marked 'Completed' only if the payment is 'Paid'.", 'danger')
                    return redirect(url_for('repair.view_repair', repair_id=repair_id))

                # Update status
                repair.progress_status = new_status_enum
                db.session.commit()

                flash(f"Repair status updated to '{new_status_enum.value}'.", 'success')
                logger.info(f"User {current_user.username} updated status for repair {repair.reference_number} to {new_status_enum.value}.")
            except KeyError:
                flash("Form submission error. 'progress_status' not found.", 'danger')
                return redirect(url_for('repair.view_repair', repair_id=repair_id))  # Redirect back to repair details
                
            except SQLAlchemyError as e:
                db.session.rollback()  # Rollback the transaction in case of an error
                logger.error(f"Database error updating status for repair {repair_id}: {e}")
                flash('Database error. Could not update status.', 'danger')
                return redirect(url_for('repair.view_repair', repair_id=repair_id))  # Redirect back to repair details

            return redirect(url_for('repair.view_repair', repair_id=repair_id))  
    
        # If GET request, render the page to update the status
        return render_template('repair/update_status.html', repair=repair)

    except Exception as e:
        logger.error(f"Error in updating status for repair {repair_id}: {e}")
        flash('An error occurred while retrieving the repair details.', 'danger')
        return redirect(url_for('repair.list_repairs'))  # Redirect to the list of repairs if there's an error


@repair_bp.route('/update_payment/<int:repair_id>', methods=['GET', 'POST'])
@login_required
def update_payment(repair_id):
    """Update payment status for a repair entry."""
    try:
        repair = RepairService.query.get_or_404(repair_id)

        if request.method == 'POST':
            new_payment_status = request.form['payment_status'].upper()  # Ensure uppercase for consistency

            # Convert repair.payment_status to string
            current_payment_status = str(repair.payment_status).upper()

            # Define valid statuses
            valid_statuses = {'UNPAID', 'OVERDUE', 'PAID'}

            # Check if new status is valid
            if new_payment_status not in valid_statuses:
                flash("Invalid payment status.", 'danger')
                return redirect(url_for('repair.view_repair', repair_id=repair_id))

            # Prevent changes from 'Paid' to 'Unpaid' or 'Overdue'
            if current_payment_status == 'PAID' and new_payment_status != 'PAID':
                flash("Cannot change payment status from 'Paid' to another status.", 'danger')
                return redirect(url_for('repair.view_repair', repair_id=repair_id))

            # Update the payment status if all checks pass
            repair.payment_status = new_payment_status
            db.session.commit()

            # Log and notify the user
            logger.info(f"User {current_user.username} updated payment status for repair {repair.reference_number} to {new_payment_status}.")
            flash(f"Payment status updated to '{new_payment_status}'.", 'success')
            return redirect(url_for('repair.view_repair', repair_id=repair_id))

        return render_template('repair/update_payment.html', repair=repair)

    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Database error updating payment status for repair {repair_id}: {e}")
        flash('Database error. Could not update payment status.', 'danger')
        return redirect(url_for('repair.list_repairs'))
