

let cart = JSON.parse(localStorage.getItem('cart')) || [];

// Fetch products based on category
$(document).on('click', '.category-item', function () {
    const categoryId = $(this).data('category');

    // Show loading indicator while products load
    $('#product-list').html('<p>Loading products...</p>');
    $('#no-products').hide();

    $.ajax({
        url: `/sales/api/products/${categoryId}`,  // Flask API endpoint
        method: 'GET',
        success: function (data) {
            if (data.products && data.products.length > 0) {
                populateProducts(data.products);  // Populate with fetched data
            } else {
                $('#product-list').empty();
                $('#no-products').show();
            }
        },
        error: function () {
            showError('Failed to load products. Please try again.');
            $('#product-list').empty();
        }
    });
});

// Format currency for product prices
function formatCurrency(value) {
    return parseFloat(value).toFixed(2);
}

// Populate products list dynamically
function populateProducts(products) {
    $('#product-list').empty();

    if (products.length === 0) {
        $('#product-list').append('<p class="text-muted">No products available.</p>');
        return;
    }

    products.forEach(product => {
        let lowStockWarning = product.stock < 5 ? `<span class="text-danger">(Low)</span>` : '';
        let combinationText = product.combination_size > 1 ? `(${product.combination_size} @ Ksh ${formatCurrency(product.combination_price || 0)})` : '';

        $('#product-list').append(`
            <div class="product-item border border-primary rounded p-2 mb-3 ${product.stock === 0 ? 'disabled-card' : 'clickable'}" 
                 data-id="${product.id}" 
                 data-name="${product.name}" 
                 data-selling-price="${formatCurrency(product.selling_price || 0)}" 
                 data-combination-price="${formatCurrency(product.combination_price || 0)}" 
                 data-combination-unit-price="${formatCurrency(product.combination_unit_price || 0)}" 
                 data-stock="${product.stock}" 
                 data-combination-size="${product.combination_size || 1}">
                <h5 class="product-title">${product.name} ${lowStockWarning}</h5>
                <p class="product-price">Ksh ${formatCurrency(product.selling_price || 0)} ${combinationText}</p>
                <p class="product-stock">Stock: ${product.stock}</p>
            </div>
        `);
    });
}

// Example showError function for displaying errors (toast or modal can be used here)
function showError(message) {
    alert(message);  // Replace this with a toast or modal for better UX
}




// Function to save cart to localStorage
function saveCartToLocalStorage() {
    localStorage.setItem('cart', JSON.stringify(cart));
}

// Function to update cart display and calculate total
function updateCart() {
    $('#cart-items').empty();
    let total = 0;

    cart.forEach(item => {
        let subtotal = 0;
        const combinationSize = item.combination_size || 1;
        const fullCombinations = Math.floor(item.quantity / combinationSize);
        const remainingUnits = item.quantity % combinationSize;
        
        subtotal += fullCombinations * item.combination_price;
        const individualRemainderPrice = remainingUnits * item.selling_price;
        
        if (remainingUnits > 0) {
            subtotal += Math.min(individualRemainderPrice, item.combination_price);
        }
        
        total += subtotal;

        $('#cart-items').append(`
            <div class="cart-item">
                ${item.name} - Ksh ${item.selling_price.toFixed(2)} x ${item.quantity} = Ksh ${subtotal.toFixed(2)}
                <button class="btn btn-danger btn-sm remove-from-cart" data-id="${item.id}">X</button>
            </div>
        `);
    });

    $('#total-amount').text(total.toFixed(2));

    if (cart.length === 0) {
        $('#cart-items').append('<p class="text-muted">Your cart is empty.</p>');
    }

    saveCartToLocalStorage();
}

// Logout button event to clear the cart
$(document).on('click', '#logout-button', function () {
    localStorage.removeItem('cart');
    window.location.href = "/auth/logout";
});

// Add item to cart on product click
$(document).on('click', '.product-item.clickable', function () {
    const productId = $(this).data('id');
    const productName = $(this).data('name');
    const productSellingPrice = parseFloat($(this).data('selling-price')) || 0;
    const productCombinationPrice = parseFloat($(this).data('combination-price')) || 0;
    const productCombinationUnitPrice = parseFloat($(this).data('combination-unit-price')) || 0; 
    const productStock = parseInt($(this).data('stock')) || 0;

    if (productStock === 0) {
        showError(`"${productName}" is currently out of stock.`);
        return;
    }

    const existingItem = cart.find(item => item.id === productId);

    if (existingItem) {
        if (existingItem.quantity < productStock) {
            existingItem.quantity += 1;
        } else {
            showError(`Cannot add more of "${productName}". Stock limit reached.`);
            return;
        }
    } else {
        if (productStock > 0) {
            cart.push({
                id: productId,
                name: productName,
                selling_price: productSellingPrice,
                combination_price: productCombinationPrice,
                combination_unit_price: productCombinationUnitPrice,
                quantity: 1,
                combination_size: $(this).data('combination-size') || 1
            });
        } else {
            showError(`"${productName}" is currently out of stock.`);
            return;
        }
    }
    updateCart();
});

// Remove item from cart event
$(document).on('click', '.remove-from-cart', function () {
    const productId = $(this).data('id');
    cart = cart.filter(item => item.id !== productId);
    updateCart();
});

// Clear cart button event
$(document).on('click', '#clear-cart', function () {
    if (confirm("Are you sure you want to clear the cart?")) {
        cart = [];
        localStorage.removeItem('cart');
        updateCart();
    }
});




// Initialize the cart UI on page load
$(document).ready(function() {
    updateCart(); // Update the UI based on the loaded cart from local storage
});

function showError(message) {
    // Customize this function to display the error in your desired format
    alert(message); // Example: using alert; replace with modal or toast notification if needed
}



// Handle payment method change
$('#payment-method').change(function () {
    const selectedMethod = $(this).val();
    const customerNameContainer = $('#customer-name-container');

    if (selectedMethod === 'credit') {
        customerNameContainer.show(); // Show customer name input
    } else {
        customerNameContainer.hide(); // Hide customer name input
        $('#customer-name').val(''); // Clear the input if not needed
    }
});

// Function to show error messages
function showError(message) {
    // Assuming there's a specific element for displaying error messages
    $('#error-message').text(message).show();
}

// Function to reset checkout form
function resetCheckoutForm() {
    $('#payment-method').val(''); // Reset payment method
    $('#customer-name').val(''); // Clear customer name
    $('#customer-name-container').hide(); // Hide customer name input
    $('#error-message').hide(); // Hide error message if visible
}

// Handle checkout
$('#checkout-btn').click(function () {
    if (cart.length === 0) {
        showError('Your cart is empty!');
        return;
    }

    // Populate the confirmation modal with cart items
    $('#checkout-items-list').empty(); // Clear previous items
    let total = 0;

    cart.forEach(item => {
        let subtotal = 0;
        const fullCombinations = Math.floor(item.quantity / item.combination_size);
        const remainingUnits = item.quantity % item.combination_size;

        subtotal += fullCombinations * item.combination_price;
        const individualRemainderPrice = remainingUnits * item.selling_price;
        const additionalCombinationPrice = item.combination_price;

        if (remainingUnits > 0) {
            subtotal += Math.min(individualRemainderPrice, additionalCombinationPrice);
        }

        total += subtotal;

        // Append item to the confirmation modal display
        $('#checkout-items-list').append(`
            <div class="checkout-item">
                ${item.name} - Ksh ${item.selling_price.toFixed(2)} x ${item.quantity} = Ksh ${subtotal.toFixed(2)}
            </div>
        `);
    });

    $('#checkout-total-amount').text(total.toFixed(2)); // Update the total amount display

    // Show the confirmation modal
    $('#checkoutConfirmationModal').modal('show');
});



// Confirm checkout button in modal
$(document).on('click', '#confirm-checkout-btn', function () {
    const checkoutButton = $('#checkout-btn');
    checkoutButton.prop('disabled', true); // Disable the original checkout button
    $('#checkout-loading').show(); // Show loading indicator

    const paymentMethod = $('#payment-method').val();
    const customerName = paymentMethod === 'credit' ? $('#customer-name').val().trim() : null;

    // Validate customer name if payment method is credit
    if (paymentMethod === 'credit' && !customerName) {
        showError('Please enter customer name for credit payments.');
        $('#customer-name').addClass('is-invalid'); // Highlight invalid input
        checkoutButton.prop('disabled', false); // Re-enable the checkout button
        $('#checkout-loading').hide(); // Hide loading indicator
        return;
    } else {
        $('#customer-name').removeClass('is-invalid'); // Remove highlight if valid
    }

    $.ajax({
        url: '/sales/checkout', // Adjust to your actual checkout endpoint
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ cart: cart, payment_method: paymentMethod, customer_name: customerName }),
        success: function () {
            $('#successModal').modal('show'); // Show success modal
            cart = []; // Clear cart
            updateCart(); // Update cart display
            resetCheckoutForm(); // Reset the form
        },
        error: function (xhr) {
            const errorMessage = xhr.responseJSON && xhr.responseJSON.message 
                ? xhr.responseJSON.message 
                : 'Checkout failed. Please try again.';
            showError(errorMessage);
        },
        complete: function () {
            checkoutButton.prop('disabled', false); // Re-enable the original checkout button
            $('#checkout-loading').hide(); // Hide loading indicator
            $('#checkoutConfirmationModal').modal('hide'); // Hide confirmation modal
        }
    });
});


// Function to reset the checkout form
function resetCheckoutForm() {
    $('#payment-method').val('mpesa'); // Set to default payment method
    $('#customer-name').val(''); // Clear customer name
    $('#customer-name-container').hide(); // Hide customer name input
}

// Debounce function to limit the frequency of search execution
function debounce(func, delay) {
    let timeout;
    return function (...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), delay);
    };
}

// Function to highlight matching text
function highlightMatch(text, searchTerm) {
    const regex = new RegExp(`(${searchTerm})`, 'gi');
    return text.replace(regex, '<span class="highlight">$1</span>'); // Wrap matches in a span for styling
}



// Search functionality for products and categories
const searchProductsAndCategories = debounce(function () {
    const searchTerm = $(this).val().toLowerCase();

    // Filter products
    $('.product-item').filter(function() {
        const productTitle = $(this).find('.product-title');
        const isVisible = productTitle.text().toLowerCase().includes(searchTerm);
        productTitle.html(isVisible ? highlightMatch(productTitle.text(), searchTerm) : productTitle.text()); // Highlight matches
        $(this).toggle(isVisible);
    });

    // Show or hide no products message
    $('#no-products').toggle($('#product-list').children(':visible').length === 0);

    // Filter categories
    $('.category-item').filter(function() {
        const isVisible = $(this).text().toLowerCase().includes(searchTerm);
        $(this).toggle(isVisible);
    });
}, 300); // Example delay of 300 ms for debouncing

// Event listener for search input
$('#search-input').on('input', searchProductsAndCategories);

// Function to highlight matched text in search results
function highlightMatch(text, term) {
    const escapedTerm = term.replace(/[-\/\\^$.*+?()[\]{}|]/g, '\\$&'); // Escape special regex characters
    const regex = new RegExp(`(${escapedTerm})`, 'gi'); // Case insensitive match
    return text.replace(regex, '<span class="highlight">$1</span>'); // Wrap matched text in a span for styling
}

// Attach the debounced search function to input event
$('#search').on('input', debounce(function() {
    const searchTerm = $(this).val();
    if (searchTerm.trim() !== '') { // Only highlight if the input is not empty
        searchProductsAndCategories.call(this);
    }
}, 300));

// Utility function to show error messages
function showError(message) {
    $('#error-message').text(message).show(); // Display error message
    $('#error-message').addClass('error-highlight'); // Add a class for styling
    setTimeout(() => {
        $('#error-message').removeClass('error-highlight'); // Remove class before hiding
        $('#error-message').hide(); // Hide after 5 seconds
    }, 5000); // Hide after 5 seconds
}


// Function to handle card animations and display adjustments
function animateCardsOnHover() {
    const productItems = document.querySelectorAll('.product-item');
    productItems.forEach(item => {
        item.addEventListener('mouseover', () => {
            item.style.transform = 'scale(1.02)';
        });
        item.addEventListener('mouseleave', () => {
            item.style.transform = 'scale(1)';
        });
    });
}

document.addEventListener('DOMContentLoaded', animateCardsOnHover);