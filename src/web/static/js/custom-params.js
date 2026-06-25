// Manages the "Custom Parameters" form section.
// - "+ Add parameter" appends a name+value row pair
// - The name input drives the value input's `name` attribute (snake_cased),
//   so the server-side handler picks it up via the existing extras path
// - Empty-name rows are skipped on submit (value input gets disabled)

const NAME_NORMALIZE = /[^a-z0-9_]+/g;

function normalize(raw) {
    return raw.trim().toLowerCase().replace(NAME_NORMALIZE, '_').replace(/^_+|_+$/g, '');
}

function collidesWithSchemaField(name, valueInput) {
    const matches = document.getElementsByName(name);
    for (const el of matches) {
        if (el !== valueInput && !el.classList.contains('custom-param-value')) {
            return true;
        }
    }
    return false;
}

function wireRow(row) {
    const nameInput = row.querySelector('.custom-param-name');
    const valueInput = row.querySelector('.custom-param-value');
    const removeBtn = row.querySelector('.custom-param-remove');
    const errorEl = document.createElement('p');
    errorEl.className = 'col-span-3 text-xs text-red-400 hidden';
    row.appendChild(errorEl);

    const sync = () => {
        const n = normalize(nameInput.value);
        if (!n) {
            valueInput.disabled = true;
            valueInput.removeAttribute('name');
            errorEl.classList.add('hidden');
            return;
        }
        if (collidesWithSchemaField(n, valueInput)) {
            valueInput.disabled = true;
            valueInput.removeAttribute('name');
            errorEl.textContent = `"${n}" is already a schema field — pick a different name.`;
            errorEl.classList.remove('hidden');
            return;
        }
        valueInput.name = n;
        valueInput.disabled = false;
        errorEl.classList.add('hidden');
    };
    nameInput.addEventListener('input', sync);
    nameInput.addEventListener('blur', () => {
        const n = normalize(nameInput.value);
        if (n && nameInput.value !== n) nameInput.value = n;
        sync();
    });
    removeBtn.addEventListener('click', () => row.remove());
    sync();
}

function addRow(list) {
    const row = document.createElement('div');
    row.className = 'custom-param-row grid grid-cols-[1fr_1fr_auto] gap-2 items-center';
    row.innerHTML = `
        <input type="text" class="custom-param-name rounded-md border-gray-600 bg-gray-900 text-white text-sm"
               list="custom-param-suggestions" placeholder="parameter_name">
        <input type="text" class="custom-param-value rounded-md border-gray-600 bg-gray-900 text-white text-sm"
               placeholder="value">
        <button type="button" class="custom-param-remove text-red-400 hover:text-red-300 px-2"
                aria-label="Remove parameter">×</button>
    `;
    list.appendChild(row);
    wireRow(row);
    row.querySelector('.custom-param-name').focus();
}

export function initCustomParams() {
    const list = document.getElementById('custom-params-list');
    const addBtn = document.getElementById('add-custom-param');
    if (!list || !addBtn) return;

    list.querySelectorAll('.custom-param-row').forEach(wireRow);
    addBtn.addEventListener('click', () => addRow(list));
}
