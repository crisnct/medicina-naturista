import { HerbsStrip } from "./HerbsStrip";
import doctorPortrait from "../assets/dr-cuisor.webp";

export function Hero() {
  return (
    <section id="hero-panel" aria-labelledby="hero-title">
      <div className="hero-kicker">
        🌿Asistent AI de medicină naturistă bazat pe surse locale
      </div>
      <HerbsStrip />
      <img className="hero-doctor" src={doctorPortrait} alt="Dr. Cuișor" />
      <div className="hero-title-block">
        <h1 id="hero-title">Remedii Naturiste</h1>
        <p className="hero-byline">de la Dr. Cuișor</p>
        <p className="hero-description">
          Descrieți problema cu care vă confruntați și primiți un raport informativ, clar și ușor de consultat.
          Informațiile sunt orientative și nu înlocuiesc consultul sau îngrijirea medicală.
        </p>
      </div>
    </section>
  );
}
