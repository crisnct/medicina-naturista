export function OwnerNotice({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div id="owner-notice">
      <div className="owner-notice-panel" role="alert">
        {message}
      </div>
    </div>
  );
}
