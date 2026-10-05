import stripUrl from "../assets/herbs-strip.webp";

// Size of herbs-strip.webp, in pixels; the aspect ratio reserves its height.
const STRIP_WIDTH = 1990;
const STRIP_HEIGHT = 317;

// Decorative strip of herbs along the bottom edge of the hero.
export function HerbsStrip() {
  return (
    <div className="herbs-strip" style={{ aspectRatio: STRIP_WIDTH / STRIP_HEIGHT }} aria-hidden="true">
      <img src={stripUrl} alt="" />
    </div>
  );
}
