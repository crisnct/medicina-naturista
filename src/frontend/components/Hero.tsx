import type { ReactNode } from "react";
import { tr } from "../lib/texts";
import { HerbsStrip } from "./HerbsStrip";
import doctorPortrait from "../assets/dr-cuisor.webp";

export function Hero({ controls }: { controls?: ReactNode }) {
  return (
    <section id="hero-panel" aria-labelledby="hero-title">
      <div className="hero-header">
        <div className="hero-kicker">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M19 4c-7-1-14 3-13 9 1 5 7 6 10 2 2-3 3-7 3-11Z" stroke="currentColor" strokeWidth="1.5" />
            <path d="m4 21 10-12M8 16l-1-4m5 0 4 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <span>{tr("interface.hero_library_label")}</span>
        </div>
        {controls}
      </div>
      <div className="hero-main">
        <div className="hero-title-block">
          <h1 id="hero-title">{tr("interface.hero_title_prefix")}<span>{tr("interface.hero_title_emphasis")}</span></h1>
          <p className="hero-description">
            {tr("interface.hero_description")}{" "}
            <span className="hero-medical-note">{tr("interface.hero_medical_notice")}</span>
          </p>
        </div>
        <figure className="hero-person">
          <div className="hero-portrait">
            <img className="hero-doctor" src={doctorPortrait} alt={tr("interface.hero_portrait_alt")} />
            <HerbsStrip />
          </div>
          <figcaption className="hero-byline">
            <strong>{tr("interface.hero_doctor_name")}</strong>
            <span>{tr("interface.hero_assistant_label")}</span>
          </figcaption>
        </figure>
      </div>
    </section>
  );
}
