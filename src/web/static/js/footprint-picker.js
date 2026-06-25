let footprintsData = [];
let footprintFilterLibrary = null;
let selectedFootprintLibrary = null;

export async function initFootprintPicker() {
    const input = document.getElementById('footprint');
    const searchInput = document.getElementById('footprint-search');
    const resultsDiv = document.getElementById('footprint-results');
    const filterBadge = document.getElementById('footprint-filter');
    const selectedLibraryDiv = document.getElementById('footprint-selected-library');

    if (!input || !searchInput || !resultsDiv) {
        return;
    }

    try {
        const [system, repo] = await Promise.all([
            fetch('/static/indexes/footprints.json').then((r) => r.json()).catch(() => []),
            fetch('/api/repo/footprints').then((r) => r.json()).catch(() => []),
        ]);
        const seen = new Set();
        footprintsData = [...repo, ...system].filter((e) => {
            const k = `${e.library}:${e.name}`;
            if (seen.has(k)) return false;
            seen.add(k);
            return true;
        });

        if (input.value && input.value.includes(':')) {
            const [lib, name] = input.value.split(':');
            selectedFootprintLibrary = lib;
            searchInput.value = name;
            updateSelectedLibraryBadge();
        }
    } catch (err) {
        console.error('Failed to load footprints:', err);
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

        if (footprintFilterLibrary) {
            footprintsData
                .filter((f) => f.library === footprintFilterLibrary)
                .forEach((f) => {
                    const score = scoreMatch(f.name, q);
                    if (score > 0 || q === '') {
                        results.push({
                            score,
                            type: 'footprint',
                            value: `${f.library}:${f.name}`,
                            text: f.name,
                            library: f.library,
                        });
                    }
                });
            results.sort((a, b) => b.score - a.score || a.text.localeCompare(b.text));
            return results.slice(0, maxResults);
        }

        const libMatches = [];
        const uniqueLibraries = [...new Set(footprintsData.map((f) => f.library))];

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

            const libFootprints = footprintsData
                .filter((f) => f.library === m.lib)
                .slice(0, 5);
            libFootprints.forEach((f) => {
                results.push({
                    score: 40,
                    type: 'footprint',
                    value: `${f.library}:${f.name}`,
                    text: f.name,
                    library: f.library,
                });
            });
        });

        footprintsData.forEach((f) => {
            if (matchingLibSet.has(f.library)) return;
            const score = scoreMatch(f.name, q);
            if (score > 0) {
                results.push({
                    score,
                    type: 'footprint',
                    value: `${f.library}:${f.name}`,
                    text: f.name,
                    library: f.library,
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
                                data-value="${s.value}" data-type="library">
                                <i class="fa-solid fa-folder mr-2"></i>${s.text}
                                <span class="text-xs text-blue-200 ml-2">[Enter] to filter</span>
                            </div>`;
                }
                return `<div class="sym-option px-3 py-2 ${
                    isHighlighted ? 'bg-blue-600' : 'hover:bg-gray-700'
                } cursor-pointer text-sm transition-colors"
                            data-value="${s.value}" data-type="footprint">
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
        if (footprintFilterLibrary) {
            searchInput.placeholder = `Searching in ${footprintFilterLibrary}...`;
            filterBadge.innerHTML = `<span class="inline-flex items-center gap-1 px-2 py-1 bg-blue-600 text-white rounded text-xs">
                <i class="fa-solid fa-microchip"></i>${footprintFilterLibrary}
                <button type="button" onclick="clearFootprintFilter()" class="hover:text-blue-200 ml-1 font-bold">×</button>
            </span>`;
        } else {
            searchInput.placeholder = 'Search footprint or library...';
            filterBadge.innerHTML = '';
        }
    }

    function updateSelectedLibraryBadge() {
        if (selectedFootprintLibrary) {
            selectedLibraryDiv.innerHTML = `<span class="inline-flex items-center gap-1 px-2 py-1 bg-green-700 text-white rounded text-xs">
                <i class="fa-solid fa-folder"></i>${selectedFootprintLibrary}
                <button type="button" onclick="clearFootprintSelection()" class="hover:text-green-200 ml-1 font-bold">×</button>
            </span>`;
            selectedLibraryDiv.classList.remove('hidden');
        } else {
            selectedLibraryDiv.innerHTML = '';
            selectedLibraryDiv.classList.add('hidden');
        }
    }

    function selectFootprint(value) {
        input.value = value;
        if (value.includes(':')) {
            const [lib, name] = value.split(':');
            selectedFootprintLibrary = lib;
            searchInput.value = name;
        } else {
            selectedFootprintLibrary = null;
            searchInput.value = value;
        }
        updateSelectedLibraryBadge();
        resultsDiv.classList.add('hidden');
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

        if (type === 'library') {
            footprintFilterLibrary = value;
            searchInput.value = '';
            searchInput.placeholder = `Search in ${value}...`;
            updateFilterBadge();
            resultsDiv.classList.add('hidden');
            isFirstRender = true;
            searchInput.focus();
        } else {
            selectFootprint(value);
        }
    });

    searchInput.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            if (footprintFilterLibrary) {
                clearFootprintFilterLocal();
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
                    footprintFilterLibrary = selected.value;
                    searchInput.value = '';
                    updateFilterBadge();
                    resultsDiv.classList.add('hidden');
                    isFirstRender = true;
                    searchInput.focus();
                } else {
                    selectFootprint(selected.value);
                }
            }
        }
    });

    function clearFootprintFilterLocal() {
        footprintFilterLibrary = null;
        searchInput.placeholder = 'Search footprint or library...';
        updateFilterBadge();
        if (searchInput.value) {
            const suggestions = getSuggestions(searchInput.value);
            renderSuggestions(suggestions);
        }
    }

    function clearFootprintSelectionLocal() {
        selectedFootprintLibrary = null;
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

    window.clearFootprintFilter = clearFootprintFilterLocal;
    window.clearFootprintSelection = clearFootprintSelectionLocal;
}

export { footprintsData, footprintFilterLibrary };
