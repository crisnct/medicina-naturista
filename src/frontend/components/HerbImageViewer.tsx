import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { tr } from "../lib/texts";

// Native modal dialogs keep keyboard focus inside and make the page beneath inert.
export function HerbImageViewer({ src, herbName, onClose }: {
  src: string;
  herbName: string;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    dialog.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      dialog.close();
      document.body.style.overflow = previousOverflow;
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) {
        previousFocus.focus({ preventScroll: true });
      }
    };
  }, []);

  return createPortal(
    <dialog
      ref={dialogRef}
      className="herb-image-viewer"
      aria-label={tr("interface.herb_image_title", { herb_name: herbName })}
      onCancel={(event) => { event.preventDefault(); onClose(); }}
    >
      <div className="herb-image-viewer-toolbar">
        <h2>{herbName}</h2>
        <button type="button" className="herb-image-viewer-close" autoFocus
          aria-label={tr("interface.herb_image_close")} onClick={onClose}>×</button>
      </div>
      <img className="herb-image-viewer-picture" src={src} alt={herbName} />
    </dialog>,
    document.body,
  );
}
