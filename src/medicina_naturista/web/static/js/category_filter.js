() => {
    const root = document.getElementById("app-shell") || document;
    const panel = () => root.querySelector("#category-filter-panel");
    const getHiddenField = () => document.querySelector("#category-selection textarea, #category-selection input");

    // A node's own checkbox counts toward the serialized selection only when
    // its <li class="cat-node"> carries data-real="1" (own_documents > 0):
    // a purely structural branch is never a chunk's category_id, see
    // medicina_naturista.ai.categories.CategoryTree.known_ids().
    const realCheckboxSelector = '.cat-node[data-real="1"] > .cat-row .cat-checkbox';

    // Every real checkbox inside (and including, if real) the given node.
    const realCheckboxesWithin = (li) => {
        const boxes = [];
        if (li.dataset.real === "1") {
            const own = li.querySelector(":scope > .cat-row .cat-checkbox");
            if (own) boxes.push(own);
        }
        li.querySelectorAll(":scope > .cat-children > .cat-node").forEach((child) => {
            boxes.push(...realCheckboxesWithin(child));
        });
        return boxes;
    };

    // Checking (or unchecking) a node cascades the same state to every real
    // checkbox under it, including its own if it has documents directly in it.
    const applyState = (li, checked) => {
        realCheckboxesWithin(li).forEach((box) => { box.checked = checked; });
    };

    // Recompute every ancestor's own checkbox from its descendants: fully
    // checked, fully unchecked, or indeterminate ("mixed") when only some of
    // its real descendants are checked. Native `.indeterminate` is what
    // renders the dash/mixed look and is what assistive tech announces.
    const recomputeAncestors = (li) => {
        let node = li.parentElement && li.parentElement.closest(".cat-node");
        while (node) {
            const boxes = realCheckboxesWithin(node);
            const total = boxes.length;
            const checkedCount = boxes.filter((box) => box.checked).length;
            const rowBox = node.querySelector(":scope > .cat-row .cat-checkbox");
            if (rowBox) {
                rowBox.checked = total > 0 && checkedCount === total;
                rowBox.indeterminate = checkedCount > 0 && checkedCount < total;
            }
            node = node.parentElement && node.parentElement.closest(".cat-node");
        }
    };

    const updateStatus = (count) => {
        const status = panel()?.querySelector("[data-category-status]");
        if (!status) return;
        status.textContent = count === 0
            ? "Se caută în toate sursele."
            : `Se caută doar în ${count} categorie${count === 1 ? "" : "i"} selectată${count === 1 ? "" : "e"}.`;
    };

    // Push the checked real category ids into the hidden Gradio textbox the
    // same way app.js forwards the "Generează rețeta" search id: set the
    // value through the native setter (so React/Gradio notices it) and
    // dispatch "input" so the component picks it up.
    const serialize = () => {
        const ids = Array.from(root.querySelectorAll(realCheckboxSelector))
            .filter((box) => box.checked)
            .map((box) => box.dataset.id);
        const field = getHiddenField();
        if (field) {
            const prototype = field.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
            Object.getOwnPropertyDescriptor(prototype, "value").set.call(field, JSON.stringify(ids));
            field.dispatchEvent(new Event("input", { bubbles: true }));
        }
        updateStatus(ids.length);
    };

    if (!window.__naturistCategoryFilterBound) {
        window.__naturistCategoryFilterBound = true;

        // Expand/collapse a branch. Kept separate from the checkbox so
        // checking a box never toggles its own row's expansion.
        document.addEventListener("click", (event) => {
            const toggle = event.target.closest?.(".cat-toggle:not(.cat-toggle-spacer)");
            if (!toggle || !panel()?.contains(toggle)) return;
            const li = toggle.closest(".cat-node");
            const children = li?.querySelector(":scope > .cat-children");
            if (!children) return;
            const expanded = toggle.getAttribute("aria-expanded") === "true";
            toggle.setAttribute("aria-expanded", String(!expanded));
            children.hidden = expanded;
            toggle.textContent = expanded ? "▸" : "▾";
        });

        document.addEventListener("change", (event) => {
            const box = event.target.closest?.(".cat-checkbox");
            if (!box || !panel()?.contains(box)) return;
            const li = box.closest(".cat-node");
            if (!li) return;
            // A click always leaves a native checkbox fully checked or fully
            // unchecked (never indeterminate), even if it was mixed before —
            // exactly the "clicking a mixed box selects everything under it"
            // behaviour wanted here.
            applyState(li, box.checked);
            recomputeAncestors(li);
            serialize();
        });

        document.addEventListener("click", (event) => {
            if (!event.target.closest?.("[data-category-reset]")) return;
            if (!panel()?.contains(event.target)) return;
            root.querySelectorAll(".category-tree .cat-checkbox").forEach((box) => {
                box.checked = false;
                box.indeterminate = false;
            });
            serialize();
        });
    }

    updateStatus(Array.from(root.querySelectorAll(realCheckboxSelector)).filter((box) => box.checked).length);
}
