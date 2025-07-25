// assign_property.js: Page-specific JS for assign_property.html

document.addEventListener('DOMContentLoaded', function () {
  // Theme initialization
  const theme = localStorage.getItem('theme') || 'light';
  if (theme === 'dark') {
    document.body.classList.add('dark');
  }

  // Theme toggle buttons
  const themeToggles = [
    document.getElementById('themeToggle'),
    document.getElementById('mobileThemeToggle'),
  ];
  themeToggles.forEach((toggle) => {
    if (toggle) {
      toggle.addEventListener('click', () => {
        document.body.classList.toggle('dark');
        localStorage.setItem(
          'theme',
          document.body.classList.contains('dark') ? 'dark' : 'light'
        );
        showNotification('Theme changed successfully', 'success');
      });
    }
  });

  // Mobile menu toggle
  const mobileMenuToggle = document.getElementById('mobileMenuToggle');
  const mobileMenu = document.getElementById('mobileMenu');
  if (mobileMenuToggle && mobileMenu) {
    mobileMenuToggle.addEventListener('click', () => {
      mobileMenu.classList.toggle('hidden');
      const icon = mobileMenuToggle.querySelector('i');
      icon.classList.toggle('fa-bars');
      icon.classList.toggle('fa-times');
    });
  }

  // Form elements
  const form = document.getElementById('assignForm');
  const tenantSelect = document.getElementById('tenant_id');
  const propertySelect = document.getElementById('property_id');
  const unitSelect = document.getElementById('unit_id');
  const submitBtn = form?.querySelector('.btn-submit');
  const loading = document.querySelector('.loading');
  const progressFill = document.querySelector('.progress-fill');
  let isFormDirty = false;

  function updateProgress() {
    const fields = [tenantSelect, propertySelect, unitSelect];
    const filledFields = fields.filter((field) => field?.value && field.value.trim() !== '').length;
    const progress = (filledFields / fields.length) * 100;
    if (progressFill) {
      progressFill.style.width = `${progress}%`;
    }
  }

  function validateField(field) {
    const existingError = field.parentNode.querySelector('.text-danger');
    if (existingError) existingError.remove();
    field.classList.remove('error');

    if (field.hasAttribute('required') && !field.value.trim()) {
      showError(field, 'This field is required');
      return false;
    }
    return true;
  }

  function showError(field, message) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'text-danger';
    errorDiv.textContent = message;
    field.parentNode.appendChild(errorDiv);
    field.classList.add('error');
    field.parentNode.classList.add('has-error');
    setTimeout(() => field.parentNode.classList.remove('has-error'), 1000);
  }

  [tenantSelect, propertySelect, unitSelect].forEach((field) => {
    if (field) {
      field.addEventListener('change', () => {
        isFormDirty = true;
        validateField(field);
        updateProgress();
      });
    }
  });

  const cancelBtn = document.getElementById('cancelBtn');
  if (cancelBtn) {
    cancelBtn.addEventListener('click', function (e) {
      if (isFormDirty && !confirm('Are you sure you want to cancel? Unsaved changes will be lost.')) {
        e.preventDefault();
      }
    });
  }

  function showNotification(message, type) {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);
    setTimeout(() => notification.remove(), 3000);
  }

  // Accessibility: Focus management for select and buttons
  form?.querySelectorAll('select, button').forEach((element) => {
    element.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && element.tagName !== 'BUTTON') {
        e.preventDefault();
        const formElements = Array.from(form.querySelectorAll('select, button'));
        const currentIndex = formElements.indexOf(element);
        const nextElement = formElements[currentIndex + 1];
        if (nextElement) nextElement.focus();
      }
    });
  });

  // Close mobile menu on link click
  if (mobileMenu) {
    mobileMenu.querySelectorAll('a').forEach((link) => {
      link.addEventListener('click', () => {
        mobileMenu.classList.add('hidden');
        const icon = mobileMenuToggle.querySelector('i');
        icon.classList.remove('fa-times');
        icon.classList.add('fa-bars');
      });
    });
  }

  // Escape key closes mobile menu
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && mobileMenu) {
      mobileMenu.classList.add('hidden');
      const icon = mobileMenuToggle.querySelector('i');
      icon.classList.remove('fa-times');
      icon.classList.add('fa-bars');
    }
  });

  // Lazy load all images
  document.querySelectorAll('img').forEach(img => {
    if (!img.hasAttribute('loading')) {
      img.setAttribute('loading', 'lazy');
    }
  });

  // Initial progress setup
  updateProgress();
});
