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
        // "Generează rețeta" lives inside chat messages, which cannot hold Gradio
        // components: forward the click (with its search id) to the hidden controls.
        document.addEventListener("click", (event) => {
            const inline = event.target.closest?.(".generate-inline");
            if (!inline || inline.disabled) return;
            const searchId = [...inline.classList].find((name) => name.startsWith("gen-"))?.slice(4);
            const field = document.querySelector("#generate-target textarea, #generate-target input");
            const trigger = document.querySelector("#generate-recipe");
            if (!searchId || !field || !trigger) return;
            const prototype = field.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
            Object.getOwnPropertyDescriptor(prototype, "value").set.call(field, searchId);
            field.dispatchEvent(new Event("input", { bubbles: true }));
            window.setTimeout(() => trigger.click(), 60);
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
