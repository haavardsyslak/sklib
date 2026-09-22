const navigationToggle = document.querySelector('.nav-toggle');
const sidebar = document.getElementById('sidebar');

function setNavigationOpen(open) {
    if (!navigationToggle || !sidebar) return;
    sidebar.classList.toggle('open', open);
    navigationToggle.setAttribute('aria-expanded', String(open));
    document.body.classList.toggle('navigation-open', open);
}

navigationToggle?.addEventListener('click', () => {
    setNavigationOpen(!sidebar?.classList.contains('open'));
});

sidebar?.addEventListener('click', (event) => {
    if (event.target.closest('a')) setNavigationOpen(false);
});

document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') setNavigationOpen(false);
});
