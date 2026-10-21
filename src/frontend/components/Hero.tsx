import { HerbsStrip } from "./HerbsStrip";
import doctorPortrait from "../assets/dr-cuisor.webp";

export function Hero() {
  return (
    <section id="hero-panel" aria-labelledby="hero-title">
      <div className="hero-kicker">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M19 4c-7-1-14 3-13 9 1 5 7 6 10 2 2-3 3-7 3-11Z" stroke="currentColor" strokeWidth="1.5" />
          <path d="m4 21 10-12M8 16l-1-4m5 0 4 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <span>Biblioteca naturistă</span>
      </div>
      <div className="hero-main">
        <div className="hero-title-block">
          <h1 id="hero-title">Remedii naturiste <span>adjuvante</span></h1>
          <p className="hero-description">
            Informații despre plante și remedii, explicate pe baza cărților din bibliotecă.{" "}
            <span className="hero-medical-note">Nu înlocuiesc consultația medicală.</span>
          </p>
        </div>
        <figure className="hero-person">
          <div className="hero-portrait">
            <img className="hero-doctor" src={doctorPortrait} alt="Personajul virtual Dr. Cuișor" />
            <HerbsStrip />
          </div>
          <figcaption className="hero-byline">
            <strong>Dr. Cuișor</strong>
            <span>Asistent virtual AI</span>
          </figcaption>
        </figure>
      </div>
    </section>
  );
}
