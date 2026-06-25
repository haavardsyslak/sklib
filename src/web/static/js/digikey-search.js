let pendingDigiKeyFields = null;
let currentResults = [];

export function initDigikeySearch() {
    const mpnInput = document.getElementById('mpn');
    const searchBtn = document.getElementById('digikey-search');
    const digikeyModal = document.getElementById('digikey-modal');
    const digikeyResults = document.getElementById('digikey-results');
    const digikeyNoResults = document.getElementById('digikey-no-results');
    const digikeyError = document.getElementById('digikey-error');
    const digikeyModalClose = document.getElementById('digikey-modal-close');
    const digikeyConfirmDialog = document.getElementById('digikey-confirm-dialog');
    const overrideFields = document.getElementById('override-fields');
    const confirmCancel = document.getElementById('digikey-confirm-cancel');
    const confirmOverride = document.getElementById('digikey-confirm-override');

    if (!mpnInput || !searchBtn || !digikeyModal) {
        return;
    }

    mpnInput.addEventListener('input', function () {
        searchBtn.disabled = !this.value.trim();
    });

    searchBtn.addEventListener('click', async function () {
        const mpn = mpnInput.value.trim();
        if (!mpn) return;

        digikeyResults.innerHTML =
            '<div class="text-gray-400 text-center py-8"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Searching...</div>';
        digikeyResults.classList.remove('hidden');
        digikeyNoResults.classList.add('hidden');
        digikeyError.classList.add('hidden');
        digikeyModal.showModal();

        try {
            const response = await fetch(`/api/digikey/search?mpn=${encodeURIComponent(mpn)}`);
            const data = await response.json();

            if (data.error) {
                digikeyError.textContent = data.error;
                digikeyError.classList.remove('hidden');
                digikeyResults.classList.add('hidden');
            } else if (data.results.length === 0) {
                digikeyNoResults.classList.remove('hidden');
                digikeyResults.classList.add('hidden');
            } else {
                currentResults = data.results;
                renderDigikeyResults(data.results);
            }
        } catch (err) {
            digikeyError.textContent = err.message || 'Failed to search DigiKey';
            digikeyError.classList.remove('hidden');
            digikeyResults.classList.add('hidden');
        }
    });

    function renderDigikeyResults(results) {
        digikeyResults.innerHTML = results
            .map((product, i) => `
            <div class="p-3 bg-gray-900 rounded-md hover:bg-gray-700 cursor-pointer transition-colors"
                 data-index="${i}">
                <div class="flex justify-between">
                    <span class="font-mono text-blue-400">${escapeHtml(product.base.mpn)}</span>
                    <span class="text-gray-500 text-sm">${escapeHtml(product.base.manufacturer)}</span>
                </div>
                <div class="text-sm text-gray-300 mt-1">${escapeHtml(product.base.description)}</div>
                <div class="text-xs text-gray-500 mt-1">
                    ${escapeHtml(product.metadata.component_type)} &middot; ${escapeHtml(product.metadata.raw_category || '')}
                </div>
            </div>
        `)
            .join('');

        digikeyResults.querySelectorAll('[data-index]').forEach((el) => {
            el.addEventListener('click', () => selectDigikeyProduct(parseInt(el.dataset.index)));
        });
    }

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function selectDigikeyProduct(index) {
        digikeyModal.close();
        applyDigikeyFields(currentResults[index]);
    }

    function applyDigikeyFields(product) {
        const newFields = {
            ...product.base,
            ...product.general,
            ...product.procurement,
            ...product.parameters,
        };

        const existingFields = getCurrentFieldValues();
        const conflicts = Object.keys(newFields).filter(
            (f) => existingFields[f] && newFields[f] && newFields[f] !== existingFields[f]
        );

        if (conflicts.length > 0) {
            pendingDigiKeyFields = newFields;
            overrideFields.textContent = conflicts.join(', ');
            digikeyConfirmDialog.showModal();
        } else {
            fillFields(newFields);
        }
    }

    function getCurrentFieldValues() {
        const values = {};
        document
            .querySelectorAll('#component-form input, #component-form select, #component-form textarea')
            .forEach((el) => {
                if (el.name && el.value) values[el.name] = el.value;
            });
        return values;
    }

    function fillFields(fields) {
        Object.entries(fields).forEach(([name, value]) => {
            if (!value) return;
            const el = document.querySelector(`[name="${name}"]`);
            if (el) {
                if (el.tagName === 'SELECT') {
                    const option = [...el.options].find((opt) => opt.value === value);
                    if (option) el.value = value;
                } else {
                    el.value = value;
                }
            }
        });
    }

    digikeyModalClose.addEventListener('click', () => digikeyModal.close());
    digikeyModal.addEventListener('click', (e) => {
        if (e.target === digikeyModal) digikeyModal.close();
    });

    confirmCancel.addEventListener('click', () => {
        digikeyConfirmDialog.close();
        pendingDigiKeyFields = null;
    });

    confirmOverride.addEventListener('click', () => {
        digikeyConfirmDialog.close();
        if (pendingDigiKeyFields) fillFields(pendingDigiKeyFields);
        pendingDigiKeyFields = null;
    });
}
