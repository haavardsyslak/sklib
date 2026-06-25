import { initSymbolPicker } from './symbol-picker.js';
import { initFootprintPicker } from './footprint-picker.js';
import { initDigikeySearch } from './digikey-search.js';
import { initCustomParams } from './custom-params.js';

document.addEventListener('DOMContentLoaded', async () => {
    await initSymbolPicker();
    await initFootprintPicker();
    initDigikeySearch();
    initCustomParams();
});
