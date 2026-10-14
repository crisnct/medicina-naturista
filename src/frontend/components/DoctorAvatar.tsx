import doctorPortrait from "../assets/dr-cuisor.webp";

export function DoctorAvatar() {
  return (
    <span className="doctor-avatar">
      <img src={doctorPortrait} alt="Dr. Cuișor, asistent virtual AI" width={32} height={32} />
    </span>
  );
}
