// A duplicated browser tab can inherit sessionStorage, including its tab ID.
// Hold an exclusive Web Lock so it cannot reuse the original tab's session.
// Cross-browser admission remains the server's responsibility (one per IP).
let admission: Promise<boolean> | undefined;
let release: (() => void) | undefined;

export function claimTab(tabId: string): Promise<boolean> {
  if (!navigator.locks) return Promise.resolve(true);
  if (!admission) {
    admission = new Promise<boolean>((resolve, reject) => {
      void navigator.locks.request(`naturist-tab:${tabId}`, { ifAvailable: true }, async (lock) => {
        if (!lock) { resolve(false); return; }
        const lifetime = new Promise<void>((finish) => { release = finish; });
        resolve(true);
        await lifetime;
      }).catch(reject);
    });
  }
  return admission.then((accepted) => {
    if (!accepted) admission = undefined;
    return accepted;
  }, (error: unknown) => {
    admission = undefined;
    throw error;
  });
}

export function releaseTab(): void {
  release?.();
  release = undefined;
  admission = undefined;
}
