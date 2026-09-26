() => {
    const root = document.getElementById("app-shell") || document;
    const getField = () => root.querySelector("#health-message input, #health-message textarea");
    const getButton = () => root.querySelector("#send-message");

    const syncButton = () => {
        const field = getField();
        const button = getButton();
        if (!field || !button) return;
        const processing = button.textContent.includes("Caută");
        const disabled = processing || field.value.trim().length === 0;
        button.disabled = disabled;
        button.setAttribute("aria-disabled", String(disabled));
    };

    if (!window.__naturistComposerBound) {
        window.__naturistComposerBound = true;
        document.addEventListener("input", (event) => {
            if (event.target.matches?.("#health-message input, #health-message textarea")) syncButton();
        });
        document.addEventListener("click", (event) => {
            if (event.target.closest?.("#send-message")) {
                window.setTimeout(syncButton, 120);
            }
        });
        new MutationObserver(() => window.requestAnimationFrame(syncButton)).observe(root, {
            childList: true,
            subtree: true,
        });
    }
    syncButton();
}
