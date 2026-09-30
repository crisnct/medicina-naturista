import { useEffect, useState } from "react";
import stripUrl from "../assets/cloves/strip.webp";
import layout from "../assets/cloves/cloves.json";

// One sprite per clove, in the same order as layout.cloves (c00, c01, ...).
const spriteModules = import.meta.glob<string>("../assets/cloves/c[0-9]*.webp", {
  eager: true,
  import: "default",
});
const sprites = Object.keys(spriteModules)
  .sort()
  .map((key) => spriteModules[key]);

const HIGHLIGHT_INTERVAL_MS = 2000;

// Decorative strip of cloves: all faded, with one at a time brought to full
// visibility every 2 seconds (a different one each time).
export function ClovesStrip() {
  const [active, setActive] = useState(0);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const timer = window.setInterval(() => {
      setActive((current) => {
        const next = Math.floor(Math.random() * (layout.cloves.length - 1));
        return next >= current ? next + 1 : next;
      });
    }, HIGHLIGHT_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="cloves-strip" style={{ aspectRatio: layout.aspect }} aria-hidden="true">
      <img className="cloves-strip-base" src={stripUrl} alt="" />
      {layout.cloves.map(([left, top, width, height], index) => (
        <img
          key={index}
          className={index === active ? "clove clove-active" : "clove"}
          src={sprites[index]}
          alt=""
          style={{ left: `${left}%`, top: `${top}%`, width: `${width}%`, height: `${height}%` }}
        />
      ))}
    </div>
  );
}
