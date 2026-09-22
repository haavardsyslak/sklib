function initPicker({ searchId, valueId, resultsId, scopeId, endpoint, noun }) {
    const search = document.getElementById(searchId);
    const value = document.getElementById(valueId);
    const results = document.getElementById(resultsId);
    const scope = document.getElementById(scopeId);
    const scopeName = scope?.querySelector('span');
    const clearScopeButton = scope?.querySelector('button');
    if (!search || !value || !results || !scope || !scopeName || !clearScopeButton) {
        return;
    }

    let library = '';
    let selected = -1;
    let timer = null;
    let controller = null;

    function scheduleSearch(immediate = false) {
        window.clearTimeout(timer);
        const query = search.value.trim();
        if (!query && !library) {
            results.hidden = true;
            return;
        }
        timer = window.setTimeout(() => fetchResults(query), immediate ? 0 : 120);
    }

    async function fetchResults(query) {
        controller?.abort();
        controller = new AbortController();
        showMessage(`Searching ${library || 'all libraries'}…`);
        const parameters = new URLSearchParams();
        if (query) parameters.set('q', query);
        if (library) parameters.set('library', library);

        try {
            const response = await fetch(`${endpoint}?${parameters}`, {
                signal: controller.signal,
            });
            if (!response.ok) {
                throw new Error(`${response.status} ${response.statusText}`);
            }
            renderResults(await response.json());
        } catch (error) {
            if (error.name !== 'AbortError') {
                showMessage(
                    `${noun} search unavailable. Exact Library:Name values still work.`,
                );
                console.warn(`Could not search ${noun}s:`, error);
            }
        }
    }

    function renderResults(payload) {
        results.replaceChildren();
        if (payload.libraries.length) {
            addHeading('Libraries');
            for (const item of payload.libraries) {
                const button = resultButton(item.name, `${item.count} ${noun}s`);
                button.dataset.kind = 'library';
                button.dataset.library = item.name;
                results.append(button);
            }
        }
        if (payload.items.length) {
            addHeading(noun === 'symbol' ? 'Symbols' : 'Footprints');
            for (const item of payload.items) {
                const fullName = `${item.library}:${item.name}`;
                const button = resultButton(fullName, item.source);
                button.dataset.kind = 'item';
                button.dataset.value = fullName;
                results.append(button);
            }
        }
        if (!payload.libraries.length && !payload.items.length) {
            showMessage(
                `No indexed ${noun} found. Exact Library:Name values still work.`,
            );
            return;
        }
        if (payload.total > payload.items.length) {
            const message = document.createElement('div');
            message.className = 'picker-message';
            message.textContent = `Showing ${payload.items.length} of ${payload.total} matches. Refine search for more.`;
            results.append(message);
        }
        selected = 0;
        updateSelection(0);
        results.hidden = false;
    }

    function resultButton(text, detail) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'picker-result';
        button.textContent = text;
        const source = document.createElement('span');
        source.className = 'picker-source';
        source.textContent = detail;
        button.append(source);
        return button;
    }

    function addHeading(text) {
        const heading = document.createElement('div');
        heading.className = 'picker-heading';
        heading.textContent = text;
        results.append(heading);
    }

    function showMessage(text) {
        results.replaceChildren();
        const message = document.createElement('div');
        message.className = 'picker-message';
        message.textContent = text;
        results.append(message);
        selected = -1;
        results.hidden = false;
    }

    function activate(button) {
        if (button.dataset.kind === 'library') {
            selectLibrary(button.dataset.library);
        } else {
            value.value = button.dataset.value;
            search.value = button.dataset.value;
            results.hidden = true;
        }
    }

    function selectLibrary(name) {
        library = name;
        scopeName.textContent = name;
        scope.hidden = false;
        search.value = '';
        value.value = '';
        search.focus();
        scheduleSearch(true);
    }

    function clearLibrary() {
        library = '';
        scope.hidden = true;
        results.hidden = true;
        if (!value.value) search.value = '';
        search.focus();
    }

    function updateSelection(next) {
        const buttons = [...results.querySelectorAll('.picker-result')];
        if (!buttons.length) return;
        selected = Math.max(0, Math.min(next, buttons.length - 1));
        buttons.forEach((button, index) => {
            button.classList.toggle('selected', index === selected);
        });
        buttons[selected].scrollIntoView({ block: 'nearest' });
    }

    results.addEventListener('mousedown', (event) => {
        const button = event.target.closest('button.picker-result');
        if (!button) return;
        event.preventDefault();
        activate(button);
    });

    clearScopeButton.addEventListener('click', clearLibrary);

    search.addEventListener('input', () => {
        const query = search.value.trim();
        if (query !== value.value) {
            value.value = query.includes(':') ? query : '';
        }
        scheduleSearch();
    });

    search.addEventListener('focus', () => {
        if (search.value.trim() || library) scheduleSearch(true);
    });

    search.addEventListener('keydown', (event) => {
        const popupOpen = !results.hidden;
        const controlKey = event.ctrlKey && !event.altKey && !event.metaKey;
        const key = event.key.toLowerCase();
        const nextKey = event.key === 'ArrowDown' || (controlKey && key === 'n');
        const previousKey = event.key === 'ArrowUp' || (controlKey && key === 'p');

        if (event.key === 'Escape') {
            window.clearTimeout(timer);
            controller?.abort();
            if (popupOpen) {
                event.preventDefault();
                controller?.abort();
                results.hidden = true;
            } else if (library) {
                event.preventDefault();
                clearLibrary();
            }
        } else if (popupOpen && nextKey) {
            event.preventDefault();
            updateSelection(selected + 1);
        } else if (popupOpen && previousKey) {
            event.preventDefault();
            updateSelection(selected - 1);
        } else if (popupOpen && event.key === 'Enter') {
            const buttons = [...results.querySelectorAll('.picker-result')];
            if (selected >= 0 && buttons[selected]) {
                event.preventDefault();
                activate(buttons[selected]);
            }
        }
    });

    search.addEventListener('blur', () => {
        window.clearTimeout(timer);
        window.setTimeout(() => {
            controller?.abort();
            results.hidden = true;
        }, 100);
    });
}

initPicker({
    searchId: 'symbol-search',
    valueId: 'symbol',
    resultsId: 'symbol-results',
    scopeId: 'symbol-library',
    endpoint: '/api/kicad/symbols',
    noun: 'symbol',
});

initPicker({
    searchId: 'footprint-search',
    valueId: 'footprint',
    resultsId: 'footprint-results',
    scopeId: 'footprint-library',
    endpoint: '/api/kicad/footprints',
    noun: 'footprint',
});

function initDigikeySearch() {
    const button = document.getElementById('digikey-search');
    const mpn = document.getElementById('mpn');
    const status = document.getElementById('digikey-status');
    const results = document.getElementById('digikey-results');
    const stock = document.getElementById('digikey-stock');
    const stockValue = document.getElementById('digikey-stock-value');
    const componentType = document.querySelector('[name="component_type"]')?.value;
    if (!button || !mpn || !status || !results || !stock || !stockValue) return;

    button.addEventListener('click', async () => {
        const query = mpn.value.trim();
        if (!query) {
            status.textContent = 'Enter a manufacturer part number first.';
            return;
        }
        button.disabled = true;
        status.textContent = 'Searching DigiKey…';
        results.hidden = true;
        results.replaceChildren();
        try {
            const token = document.querySelector('meta[name="csrf-token"]')?.content || '';
            const response = await fetch(
                `/api/suppliers/digikey/search?q=${encodeURIComponent(query)}`,
                { headers: { 'X-CSRF-Token': token } },
            );
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.error || 'DigiKey search failed');
            renderSupplierResults(payload.results || []);
            status.textContent = payload.results?.length
                ? 'Select a result to review and apply it.'
                : 'No results found.';
        } catch (error) {
            status.textContent = error.message;
        } finally {
            button.disabled = false;
        }
    });

    function renderSupplierResults(products) {
        results.replaceChildren();
        for (const product of products) {
            const item = document.createElement('button');
            item.type = 'button';
            item.className = 'supplier-result';
            const title = document.createElement('strong');
            title.textContent = `${product.mpn} · ${product.manufacturer}`;
            const description = document.createElement('span');
            description.textContent = product.description;
            const category = document.createElement('span');
            category.textContent = product.component_type
                ? `${product.component_type} · ${product.raw_category}`
                : `Unknown component type · ${product.raw_category}`;
            const availability = document.createElement('span');
            availability.textContent = availabilityText(product);
            item.append(title, description, category, availability);
            item.addEventListener('click', () => applyProduct(product));
            results.append(item);
        }
        results.hidden = products.length === 0;
    }

    function applyProduct(product) {
        if (product.component_type && product.component_type !== componentType) {
            status.textContent = `DigiKey classified this as ${product.component_type}; current form is ${componentType}.`;
            return;
        }
        const fields = {
            mpn: product.mpn,
            manufacturer: product.manufacturer,
            description: product.description,
            manufacturer_status: product.manufacturer_status,
            datasheet: product.datasheet,
            supplier_name: product.supplier_name,
            supplier_sku: product.supplier_sku,
            supplier_url: product.supplier_url,
        };
        for (const [name, fieldValue] of Object.entries(product.specs || {})) {
            fields[`spec__${name}`] = fieldValue;
        }
        const conflicts = Object.entries(fields)
            .filter(([name, fieldValue]) => {
                const input = document.getElementById(name);
                return input && fieldValue && input.value && input.value !== fieldValue;
            })
            .map(([name]) => name.replace('spec__', ''));
        if (
            conflicts.length
            && !window.confirm(`Replace existing fields: ${conflicts.join(', ')}?`)
        ) {
            return;
        }
        const ignored = [];
        for (const [name, fieldValue] of Object.entries(fields)) {
            const input = document.getElementById(name);
            if (input && fieldValue) {
                input.value = fieldValue;
            } else if (name.startsWith('spec__') && fieldValue) {
                ignored.push(name.replace('spec__', ''));
            }
        }
        results.hidden = true;
        stockValue.textContent = availabilityText(product);
        stock.hidden = false;
        const warning = ignored.length
            ? ` Unmapped fields ignored: ${ignored.join(', ')}.`
            : '';
        status.textContent =
            `DigiKey values applied. Review every field before saving.${warning}`;
    }

    function availabilityText(product) {
        const details = [];
        if (product.stock_quantity === null || product.stock_quantity === undefined) {
            details.push('Stock unavailable');
        } else {
            details.push(`${Number(product.stock_quantity).toLocaleString()} in stock`);
        }
        if (product.minimum_order_quantity !== null
            && product.minimum_order_quantity !== undefined) {
            details.push(`MOQ ${Number(product.minimum_order_quantity).toLocaleString()}`);
        }
        if (product.packaging) details.push(product.packaging);
        return details.join(' · ');
    }
}

initDigikeySearch();

const componentForm = document.getElementById('component-form');
componentForm?.addEventListener('submit', () => {
    const submit = componentForm.querySelector('button[type="submit"]');
    if (submit) {
        submit.disabled = true;
        submit.textContent = 'Saving and building…';
    }
});
