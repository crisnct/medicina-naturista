import { DoctorAvatar } from "./DoctorAvatar";

export function OwnerNotice({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div id="owner-notice">
      <div className="owner-notice-panel chatbot-message-content" role="alert">
        <DoctorAvatar />
        <div className="chatbot-message-text">{message}</div>
      </div>
    </div>
  );
}
