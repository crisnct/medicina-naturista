import { HerbsStrip } from "./HerbsStrip";
import doctorPortrait from "../assets/dr-cuisor.webp";

export function Hero() {
  return (
    <section id="hero-panel" aria-labelledby="hero-title">
      <div className="hero-kicker">
        🌿 Informații din biblioteca naturistă
      </div>
      <HerbsStrip />
      <img className="hero-doctor" src={doctorPortrait} alt="Personajul virtual Dr. Cuișor" />
      <div className="hero-title-block">
        <h1 id="hero-title">Remedii Naturiste Adjuvante</h1>
        <p className="hero-byline">Dr. Cuișor · asistent virtual AI</p>
        <p className="hero-description">
          Informații orientative despre plante și remedii, explicate pe baza cărților și documentelor din bibliotecă. Nu înlocuiesc consultația medicală.
        </p>
      </div>
    </section>
  );
}
