import { tr } from "../lib/texts";
import doctorPortrait from "../assets/dr-cuisor.webp";

export function DoctorAvatar() {
  return (
    <span className="doctor-avatar">
      <img src={doctorPortrait} alt={tr("interface.doctor_avatar_alt")} width={32} height={32} />
    </span>
  );
}
