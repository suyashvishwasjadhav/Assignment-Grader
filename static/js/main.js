// Handle page loading
document.addEventListener('DOMContentLoaded', function() {
    // Show splash screen
    const splashScreen = document.querySelector('.splash-screen');
    
    if (splashScreen) {
        setTimeout(() => {
            splashScreen.style.opacity = '0';
            setTimeout(() => {
                splashScreen.style.display = 'none';
            }, 500);
        }, 1500);
    }

    // Setup sidebar toggle
    const sidebarToggle = document.querySelector('.sidebar-toggle');
    const sidebar = document.querySelector('.sidebar');
    const mainContent = document.querySelector('.main-content');
    
    if (sidebarToggle && sidebar && mainContent) {
        sidebarToggle.addEventListener('click', function() {
            sidebar.classList.toggle('sidebar-hidden');
            mainContent.classList.toggle('content-full');
        });
        
        // Hide sidebar on small screens by default
        if (window.innerWidth < 992) {
            sidebar.classList.add('sidebar-hidden');
            mainContent.classList.add('content-full');
        }
    }
    
    // Setup dropdown toggles
    const dropdownToggles = document.querySelectorAll('.dropdown-toggle');
    
    dropdownToggles.forEach(toggle => {
        toggle.addEventListener('click', function(e) {
            e.preventDefault();
            const dropdownMenu = this.nextElementSibling;
            dropdownMenu.classList.toggle('show');
            
            // Close dropdown when clicking outside
            document.addEventListener('click', function closeDropdown(event) {
                if (!toggle.contains(event.target) && !dropdownMenu.contains(event.target)) {
                    dropdownMenu.classList.remove('show');
                    document.removeEventListener('click', closeDropdown);
                }
            });
        });
    });
    
    // Handle flash messages
    const flashMessages = document.querySelectorAll('.alert');
    
    flashMessages.forEach(message => {
        // Add close button to flash messages
        const closeBtn = document.createElement('button');
        closeBtn.innerHTML = '&times;';
        closeBtn.classList.add('close-btn');
        closeBtn.style.cssText = 'position: absolute; right: 10px; top: 10px; background: none; border: none; font-size: 20px; cursor: pointer;';
        message.appendChild(closeBtn);
        
        // Close message when button is clicked
        closeBtn.addEventListener('click', () => {
            message.style.opacity = '0';
            setTimeout(() => {
                message.style.display = 'none';
            }, 300);
        });
        
        // Auto-hide after 5 seconds
        setTimeout(() => {
            message.style.opacity = '0';
            setTimeout(() => {
                message.style.display = 'none';
            }, 300);
        }, 5000);
    });
    
    // Theme toggle
    const themeToggle = document.getElementById('theme-toggle');
    
    if (themeToggle) {
        themeToggle.addEventListener('click', function() {
            const isDark = document.body.classList.toggle('dark-theme');
            
            // Update the icon
            const themeIcon = themeToggle.querySelector('i');
            if (themeIcon) {
                themeIcon.classList.remove('fa-sun', 'fa-moon');
                themeIcon.classList.add(isDark ? 'fa-sun' : 'fa-moon');
            }
            
            // Store theme preference in localStorage
            localStorage.setItem('theme', isDark ? 'dark' : 'light');
            
            // Also try to save user preference server-side if logged in
            try {
                fetch('/set-theme', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ theme: isDark ? 'dark' : 'light' }),
                }).catch(err => console.log('Theme preference could not be saved to server'));
            } catch(e) {
                console.log('Error saving theme preference');
            }
        });
    }
    
    // Apply theme from localStorage on page load
    document.addEventListener('DOMContentLoaded', function() {
        const savedTheme = localStorage.getItem('theme');
        if (savedTheme === 'dark' && !document.body.classList.contains('dark-theme')) {
            document.body.classList.add('dark-theme');
            
            // Update the icon if it exists
            const themeToggle = document.getElementById('theme-toggle');
            if (themeToggle) {
                const themeIcon = themeToggle.querySelector('i');
                if (themeIcon) {
                    themeIcon.classList.remove('fa-moon');
                    themeIcon.classList.add('fa-sun');
                }
            }
        }
    });
    
    // Initialize modals
    initializeModals();
});

// Modal functions
function initializeModals() {
    // Close modal when clicking outside or on the close button
    document.addEventListener('click', function(event) {
        if (event.target.matches('.modal-overlay') || event.target.matches('.modal-close')) {
            const modalOverlay = event.target.closest('.modal-overlay');
            closeModal(modalOverlay);
        }
    });
}

function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('show');
        document.body.style.overflow = 'hidden';
    }
}

function closeModal(modal) {
    if (modal) {
        modal.classList.remove('show');
        document.body.style.overflow = '';
    }
}

// Show loading spinner
function showSpinner(message = 'Loading...') {
    const spinner = document.querySelector('.spinner-overlay');
    
    if (!spinner) {
        // Create spinner if it doesn't exist
        const spinnerHtml = `
            <div class="spinner-overlay">
                <div class="spinner-container">
                    <div class="spinner"></div>
                    <div class="spinner-text">${message}</div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', spinnerHtml);
        
        // Force reflow before adding show class for animation
        document.querySelector('.spinner-overlay').offsetHeight;
        document.querySelector('.spinner-overlay').classList.add('show');
    } else {
        // Update message if spinner exists
        spinner.querySelector('.spinner-text').textContent = message;
        spinner.classList.add('show');
    }
}

function hideSpinner() {
    const spinner = document.querySelector('.spinner-overlay');
    
    if (spinner) {
        spinner.classList.remove('show');
        
        // Remove spinner after animation
        setTimeout(() => {
            spinner.remove();
        }, 300);
    }
}

// Toast notification
function showToast(message, type = 'info') {
    let container = document.querySelector('.toast-container');
    
    if (!container) {
        container = document.createElement('div');
        container.classList.add('toast-container');
        document.body.appendChild(container);
    }
    
    const id = Math.random().toString(36).substr(2, 9);
    const toast = document.createElement('div');
    toast.classList.add('toast');
    toast.id = `toast-${id}`;
    
    toast.innerHTML = `
        <div class="toast-header">
            <strong>${type.charAt(0).toUpperCase() + type.slice(1)}</strong>
            <button type="button" class="modal-close" onclick="closeToast('toast-${id}')">&times;</button>
        </div>
        <div class="toast-body">
            ${message}
        </div>
    `;
    
    container.appendChild(toast);
    
    // Force reflow before adding show class for animation
    toast.offsetHeight;
    toast.classList.add('show');
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
        closeToast(`toast-${id}`);
    }, 5000);
}

function closeToast(toastId) {
    const toast = document.getElementById(toastId);
    
    if (toast) {
        toast.classList.remove('show');
        
        // Remove toast after animation
        setTimeout(() => {
            toast.remove();
            
            // Remove container if no toasts left
            const container = document.querySelector('.toast-container');
            if (container && container.children.length === 0) {
                container.remove();
            }
        }, 300);
    }
}

// Form validation helper
function validateForm(formElement) {
    let isValid = true;
    const inputs = formElement.querySelectorAll('input, textarea, select');
    
    inputs.forEach(input => {
        if (input.hasAttribute('required') && !input.value.trim()) {
            isValid = false;
            input.classList.add('invalid');
            
            // Add error message if not already present
            let errorSpan = input.nextElementSibling;
            if (!errorSpan || !errorSpan.classList.contains('error-message')) {
                errorSpan = document.createElement('span');
                errorSpan.classList.add('error-message');
                errorSpan.style.color = 'var(--danger-color)';
                errorSpan.style.fontSize = '0.8rem';
                errorSpan.style.marginTop = '5px';
                errorSpan.textContent = 'This field is required';
                input.insertAdjacentElement('afterend', errorSpan);
            }
        } else if (input.classList.contains('invalid')) {
            input.classList.remove('invalid');
            
            // Remove error message
            const errorSpan = input.nextElementSibling;
            if (errorSpan && errorSpan.classList.contains('error-message')) {
                errorSpan.remove();
            }
        }
    });
    
    return isValid;
}

// Date formatting helper
function formatDate(dateString) {
    const date = new Date(dateString);
    const options = { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' };
    return date.toLocaleDateString('en-US', options);
}

// Format file size
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Add animation class to elements
function animateElement(element, animationClass = 'animate-fadeIn') {
    element.classList.add(animationClass);
    element.addEventListener('animationend', () => {
        element.classList.remove(animationClass);
    }, { once: true });
}

// Truncate text
function truncateText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}
