# app/home.py
from flask import Blueprint, render_template
import logging

# Define the Blueprint
home_bp = Blueprint('home', __name__)

# Create a logger instance
logger = logging.getLogger(__name__)

@home_bp.route('/')
def index():
    logger.info("Home page accessed.")
    return render_template('home.html')
