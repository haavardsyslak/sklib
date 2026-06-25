// Maps KiCad symbol properties to SKLib form field IDs
const PROPERTY_TO_FIELD_MAP = {
    'Datasheet': 'datasheet',
    'Description': 'description',
    'Manufacturer': 'manufacturer',
    'MPN': 'mpn',
    'ki_keywords': 'keywords'
};

let symbolsData = [];
let symbolFilterLibrary = null;
let selectedSymbolLibrary = null;

function autofillFromSymbolProperties(symbolData) {
    if (!symbolData.properties || Object.keys(symbolData.properties).length === 0) {
        return;
    }

    const autofilledFields = [];

    for (const [kicadProp, formFieldId] of Object.entries(PROPERTY_TO_FIELD_MAP)) {
        const propValue = symbolData.properties[kicadProp];

        if (!propValue || propValue.trim() === '') continue;

        const field = document.getElementById(formFieldId);
        if (!field) continue;

        if (formFieldId === 'keywords') {
            const existing = field.value.trim();
            if (existing) {
                const existingKeywords = existing.split(/\s+/);
                const newKeywords = propValue.split(/\s+/);
                const merged = [...new Set([...existingKeywords, ...newKeywords])];
                field.value = merged.join(' ');
            } else {
                field.value = propValue;
            }
            field.classList.add('autofilled');
            autofilledFields.push(formFieldId);
        } else {
            if (field.value.trim() === '') {
                field.value = propValue;
                field.classList.add('autofilled');
                autofilledFields.push(formFieldId);

                setTimeout(() => field.classList.remove('autofilled'), 2000);
            }
        }
    }

    if (autofilledFields.length > 0) {
        console.log(`Auto-filled ${autofilledFields.length} fields from symbol:`, autofilledFields);
    }
}

export async function initSymbolPicker() {
    const input = document.getElementById('symbol');
    const searchInput = document.getElementById('symbol-search');
    const resultsDiv = document.getElementById('symbol-results');
    const filterBadge = document.getElementById('symbol-filter');
    const selectedLibraryDiv = document.getElementById('symbol-selected-library');

    if (!input || !searchInput || !resultsDiv) {
        return;
    }

    try {
        const [system, repo] = await Promise.all([
            fetch('/static/indexes/symbols.json').then((r) => r.json()).catch(() => []),
            fetch('/api/repo/symbols').then((r) => r.json()).catch(() => []),
        ]);
        // Repo wins on duplicate (library:name) so local edits override stale system entries.
        const seen = new Set();
        symbolsData = [...repo, ...system].filter((e) => {
            const k = `${e.library}:${e.name}`;
            if (seen.has(k)) return false;
            seen.add(k);
            return true;
        });

        if (input.value && input.value.includes(':')) {
            const [lib, name] = input.value.split(':');
            selectedSymbolLibrary = lib;
            searchInput.value = name;
            updateSelectedLibraryBadge();
        }
    } catch (err) {
        console.error('Failed to load symbols:', err);
        return;
    }

    let currentSuggestions = [];
    let selectedIndex = -1;
    let isFirstRender = true;

    function scoreMatch(text, query) {
        const t = text.toLowerCase();
        const q = query.toLowerCase();
        if (t === q) return 100;
        if (t.startsWith(q)) return 80;
        if (t.includes(q)) return 60 + (q.length / t.length) * 20;
        return 0;
    }

    function getSuggestions(query, maxResults = 50) {
        const q = query.toLowerCase();
        const results = [];

        if (symbolFilterLibrary) {
            symbolsData
                .filter((s) => s.library === symbolFilterLibrary)
                .forEach((s) => {
                    const score = scoreMatch(s.name, q);
                    if (score > 0 || q === '') {
                        results.push({
                            score,
                            type: 'symbol',
                            value: `${s.library}:${s.name}`,
                            text: s.name,
                            library: s.library,
                            properties: s.properties || {},
                        });
                    }
                });
            results.sort((a, b) => b.score - a.score || a.text.localeCompare(b.text));
            return results.slice(0, maxResults);
        }

        const libMatches = [];
        const uniqueLibraries = [...new Set(symbolsData.map((s) => s.library))];

        uniqueLibraries.forEach((lib) => {
            const score = scoreMatch(lib, q);
            if (score > 0) {
                libMatches.push({ score, lib });
            }
        });
        libMatches.sort((a, b) => b.score - a.score);

        const matchingLibSet = new Set(libMatches.map((m) => m.lib));

        libMatches.forEach((m) => {
            results.push({
                score: m.score + 50,
                type: 'library',
                value: m.lib,
                text: m.lib,
                library: m.lib,
            });

            const libSymbols = symbolsData
                .filter((s) => s.library === m.lib)
                .slice(0, 5);
            libSymbols.forEach((s) => {
                results.push({
                    score: 40,
                    type: 'symbol',
                    value: `${s.library}:${s.name}`,
                    text: s.name,
                    library: s.library,
                    properties: s.properties || {},
                });
            });
        });

        symbolsData.forEach((s) => {
            if (matchingLibSet.has(s.library)) return;
            const score = scoreMatch(s.name, q);
            if (score > 0) {
                results.push({
                    score,
                    type: 'symbol',
                    value: `${s.library}:${s.name}`,
                    text: s.name,
                    library: s.library,
                    properties: s.properties || {},
                });
            }
        });

        const seen = new Set();
        const deduped = [];
        results.forEach((r) => {
            if (!seen.has(r.value)) {
                seen.add(r.value);
                deduped.push(r);
            }
        });
        deduped.sort((a, b) => b.score - a.score || a.text.localeCompare(b.text));

        return deduped.slice(0, maxResults);
    }

    function renderSuggestions(suggestions, resetIndex = false) {
        currentSuggestions = suggestions;
        if (resetIndex || isFirstRender) {
            selectedIndex = suggestions.length > 0 ? 0 : -1;
            isFirstRender = false;
        }

        if (suggestions.length === 0) {
            resultsDiv.innerHTML =
                '<div class="px-3 py-2 text-gray-500 text-sm">No results - press Escape to search all libraries</div>';
            resultsDiv.classList.remove('hidden');
            return;
        }

        resultsDiv.innerHTML = suggestions
            .map((s, i) => {
                const isHighlighted = i === selectedIndex;
                if (s.type === 'library') {
                    return `<div class="lib-header px-3 py-2 ${
                        isHighlighted ? 'bg-blue-600' : 'bg-gray-700'
                    } text-blue-300 cursor-pointer font-medium text-sm transition-colors"
                                data-value="${s.value}" data-type="library" data-index="${i}">
                                <i class="fa-solid fa-folder mr-2"></i>${s.text}
                                <span class="text-xs text-blue-200 ml-2">[Enter] to filter</span>
                            </div>`;
                }
                return `<div class="sym-option px-3 py-2 ${
                    isHighlighted ? 'bg-blue-600' : 'hover:bg-gray-700'
                } cursor-pointer text-sm transition-colors"
                            data-value="${s.value}" data-type="symbol" data-index="${i}">
                            <span class="text-gray-400">${s.library}:</span><span class="text-white">${s.text}</span>
                        </div>`;
            })
            .join('');

        resultsDiv.classList.remove('hidden');
    }

    function updateHighlight() {
        if (currentSuggestions.length === 0) return;
        Array.from(resultsDiv.children).forEach((el, i) => {
            if (i === selectedIndex) {
                el.classList.add('bg-blue-600');
                el.classList.remove('bg-gray-700', 'hover:bg-gray-700');
                el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            } else {
                el.classList.remove('bg-blue-600');
                if (el.classList.contains('lib-header')) {
                    el.classList.add('bg-gray-700');
                } else {
                    el.classList.add('hover:bg-gray-700');
                }
            }
        });
    }

    function updateFilterBadge() {
        if (symbolFilterLibrary) {
            searchInput.placeholder = `Searching in ${symbolFilterLibrary}...`;
            filterBadge.innerHTML = `<span class="inline-flex items-center gap-1 px-2 py-1 bg-blue-600 text-white rounded text-xs">
                <i class="fa-solid fa-microchip"></i>${symbolFilterLibrary}
                <button type="button" onclick="clearSymbolFilter()" class="hover:text-blue-200 ml-1 font-bold">×</button>
            </span>`;
        } else {
            searchInput.placeholder = 'Search symbol or library...';
            filterBadge.innerHTML = '';
        }
    }

    function updateSelectedLibraryBadge() {
        if (selectedSymbolLibrary) {
            selectedLibraryDiv.innerHTML = `<span class="inline-flex items-center gap-1 px-2 py-1 bg-green-700 text-white rounded text-xs">
                <i class="fa-solid fa-folder"></i>${selectedSymbolLibrary}
                <button type="button" onclick="clearSymbolSelection()" class="hover:text-green-200 ml-1 font-bold">×</button>
            </span>`;
            selectedLibraryDiv.classList.remove('hidden');
        } else {
            selectedLibraryDiv.innerHTML = '';
            selectedLibraryDiv.classList.add('hidden');
        }
    }

    function selectSymbol(symbolData) {
        const symbolValue = symbolData.value;
        input.value = symbolValue;
        if (symbolValue.includes(':')) {
            const [lib, name] = symbolValue.split(':');
            selectedSymbolLibrary = lib;
            searchInput.value = name;
        } else {
            selectedSymbolLibrary = null;
            searchInput.value = symbolValue;
        }
        updateSelectedLibraryBadge();
        resultsDiv.classList.add('hidden');

        autofillFromSymbolProperties(symbolData);

        const footprintValue = symbolData.properties?.Footprint;
        if (footprintValue && footprintValue.trim() !== '') {
            showFootprintDialog(symbolValue, footprintValue);
        }
    }

    function showFootprintDialog(symbolValue, symbolFootprint) {
        const dialog = document.getElementById('footprint-dialog');
        const dialogSymbol = document.getElementById('dialog-symbol-name');
        const dialogFootprint = document.getElementById('dialog-footprint');
        const cancelBtn = document.getElementById('dialog-cancel');
        const applyBtn = document.getElementById('dialog-apply');

        dialogSymbol.textContent = symbolValue;
        dialogFootprint.textContent = symbolFootprint;

        const cleanup = () => {
            cancelBtn.removeEventListener('click', handleCancel);
            applyBtn.removeEventListener('click', handleApply);
            dialog.removeEventListener('close', handleClose);
        };

        const handleCancel = () => {
            dialog.close('cancel');
            cleanup();
        };

        const handleApply = () => {
            const footprintInput = document.getElementById('footprint');
            const footprintSearchInput = document.getElementById('footprint-search');
            footprintInput.value = symbolFootprint;
            footprintSearchInput.value = symbolFootprint;
            dialog.close('apply');
            cleanup();
        };

        const handleClose = () => {
            cleanup();
        };

        cancelBtn.addEventListener('click', handleCancel);
        applyBtn.addEventListener('click', handleApply);
        dialog.addEventListener('close', handleClose);

        dialog.showModal();
    }

    searchInput.addEventListener('input', function () {
        const query = this.value;
        if (query.length === 0) {
            resultsDiv.classList.add('hidden');
            return;
        }
        const suggestions = getSuggestions(query);
        renderSuggestions(suggestions, true);
    });

    searchInput.addEventListener('focus', function () {
        if (this.value.length > 0) {
            const suggestions = getSuggestions(this.value);
            renderSuggestions(suggestions, true);
        }
    });

    resultsDiv.addEventListener('click', function (e) {
        const item = e.target.closest('[data-value]');
        if (!item) return;

        const value = item.dataset.value;
        const type = item.dataset.type;
        const index = parseInt(item.dataset.index, 10);

        if (type === 'library') {
            symbolFilterLibrary = value;
            searchInput.value = '';
            searchInput.placeholder = `Search in ${value}...`;
            updateFilterBadge();
            resultsDiv.classList.add('hidden');
            isFirstRender = true;
            searchInput.focus();
        } else {
            const symbolData = currentSuggestions[index];
            selectSymbol(symbolData);
        }
    });

    searchInput.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            if (symbolFilterLibrary) {
                clearSymbolFilterLocal();
                e.preventDefault();
            } else {
                resultsDiv.classList.add('hidden');
            }
            return;
        }

        if (resultsDiv.classList.contains('hidden')) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            selectedIndex = Math.min(selectedIndex + 1, currentSuggestions.length - 1);
            updateHighlight();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            selectedIndex = Math.max(selectedIndex - 1, -1);
            if (selectedIndex >= 0) updateHighlight();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (selectedIndex >= 0 && currentSuggestions[selectedIndex]) {
                const selected = currentSuggestions[selectedIndex];
                if (selected.type === 'library') {
                    symbolFilterLibrary = selected.value;
                    searchInput.value = '';
                    updateFilterBadge();
                    resultsDiv.classList.add('hidden');
                    isFirstRender = true;
                    searchInput.focus();
                } else {
                    selectSymbol(selected);
                }
            }
        }
    });

    function clearSymbolFilterLocal() {
        symbolFilterLibrary = null;
        searchInput.placeholder = 'Search symbol or library...';
        updateFilterBadge();
        if (searchInput.value) {
            const suggestions = getSuggestions(searchInput.value);
            renderSuggestions(suggestions);
        }
    }

    function clearSymbolSelectionLocal() {
        selectedSymbolLibrary = null;
        input.value = '';
        searchInput.value = '';
        updateSelectedLibraryBadge();
    }

    searchInput.addEventListener('blur', function () {
        setTimeout(() => {
            if (!resultsDiv.contains(document.activeElement)) {
                resultsDiv.classList.add('hidden');
            }
        }, 150);
    });

    document.addEventListener('click', function (e) {
        if (!searchInput.contains(e.target) && !resultsDiv.contains(e.target)) {
            resultsDiv.classList.add('hidden');
        }
    });

    window.clearSymbolFilter = clearSymbolFilterLocal;
    window.clearSymbolSelection = clearSymbolSelectionLocal;
}

export { symbolsData, symbolFilterLibrary, selectedSymbolLibrary };
