import stripUrl from "../assets/herbs-strip.webp";

// Decorative strip of herbs along the bottom edge of the hero.
export function HerbsStrip() {
  return (
    <div className="herbs-strip" aria-hidden="true">
      <img src={stripUrl} width={1990} height={317} alt="" />
    </div>
  );
}
