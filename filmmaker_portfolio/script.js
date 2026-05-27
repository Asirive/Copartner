/**
 * Filmmaker Portfolio Interactivity
 */

document.addEventListener('DOMContentLoaded', () => {
  // --- Portfolio Filtering ---
  const filterBtns = document.querySelectorAll('.filter-btn');
  const portfolioItems = document.querySelectorAll('.portfolio-item');

  filterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      // Remove active class from all buttons
      filterBtns.forEach(b => b.classList.remove('active'));
      // Add active class to clicked button
      btn.classList.add('active');

      const filterValue = btn.getAttribute('data-filter');

      portfolioItems.forEach(item => {
        if (filterValue === 'all' || item.getAttribute('data-category') === filterValue) {
          item.style.display = 'block';
          // Reset animation
          item.style.animation = 'none';
          item.offsetHeight; /* trigger reflow */
          item.style.animation = null; 
        } else {
          item.style.display = 'none';
        }
      });
    });
  });

  // --- Contact Form Submission Mock ---
  const contactForm = document.getElementById('contact-form');
  
  if (contactForm) {
    contactForm.addEventListener('submit', (e) => {
      e.preventDefault();
      
      const submitBtn = contactForm.querySelector('.submit-btn');
      const originalText = submitBtn.textContent;
      
      // Update button state
      submitBtn.textContent = 'Sending...';
      submitBtn.style.opacity = '0.7';
      submitBtn.disabled = true;

      // Simulate network request
      setTimeout(() => {
        submitBtn.textContent = 'Message Sent!';
        submitBtn.style.backgroundColor = 'var(--primary-color)';
        submitBtn.style.color = 'var(--bg-color)';
        submitBtn.style.opacity = '1';
        
        contactForm.reset();

        // Reset button after 3 seconds
        setTimeout(() => {
          submitBtn.textContent = originalText;
          submitBtn.style.backgroundColor = 'transparent';
          submitBtn.style.color = 'var(--primary-color)';
          submitBtn.disabled = false;
        }, 3000);
      }, 1500);
    });
  }
});