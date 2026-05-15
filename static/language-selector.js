/**
 * Language selector popover menu
 * Handles toggling the language selection menu and form submission
 */

document.addEventListener('DOMContentLoaded', function () {
    const languageButton = document.getElementById('language-selector-btn');
    const languagePopover = document.getElementById('language-popover');
    const languageForm = document.getElementById('language-form');
    const languageOptions = document.querySelectorAll('[data-language]');

    if (!languageButton || !languagePopover) {
        console.warn('Language selector elements not found');
        return;
    }

    /**
     * Toggle popover visibility
     */
    function togglePopover() {
        const isOpen = languagePopover.classList.contains('block');
        if (isOpen) {
            languagePopover.classList.remove('block');
            languagePopover.classList.add('hidden');
        } else {
            languagePopover.classList.remove('hidden');
            languagePopover.classList.add('block');
        }
    }

    /**
     * Close popover
     */
    function closePopover() {
        languagePopover.classList.remove('block');
        languagePopover.classList.add('hidden');
    }

    /**
     * Handle language option click
     */
    languageOptions.forEach(option => {
        option.addEventListener('click', function (e) {
            e.preventDefault();
            const languageCode = this.getAttribute('data-language');
            const hiddenSelect = document.getElementById('language-select');
            if (hiddenSelect) {
                hiddenSelect.value = languageCode;
            }
            if (languageForm) {
                languageForm.submit();
            }
            closePopover();
        });
    });

    /**
     * Toggle popover on button click
     */
    languageButton.addEventListener('click', function (e) {
        e.stopPropagation();
        togglePopover();
    });

    /**
     * Close popover when clicking outside
     */
    document.addEventListener('click', function (e) {
        const isClickInside = languagePopover.contains(e.target) || languageButton.contains(e.target);
        if (!isClickInside) {
            closePopover();
        }
    });

    /**
     * Close popover on Escape key
     */
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            closePopover();
        }
    });
});
