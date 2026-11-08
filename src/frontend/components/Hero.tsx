import type { ReactNode } from "react";
import { tr } from "../lib/texts";
import { HerbsStrip } from "./HerbsStrip";
import { BookSunflowerEmblem } from "./HeroEmblem";
import doctorPortrait from "../assets/dr-cuisor.webp";

export function Hero({ controls, documentCount }: { controls?: ReactNode; documentCount?: number | null }) {
  return (
    <section id="hero-panel" aria-labelledby="hero-title">
      <div className="hero-header">
        <div className="hero-kicker">
          <BookSunflowerEmblem />
          <span>{tr("interface.hero_library_label")}{typeof documentCount === "number" && ` - ${tr("interface.hero_document_count", { count: documentCount })}`}</span>
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
