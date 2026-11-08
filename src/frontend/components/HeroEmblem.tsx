// Emblems for the hero kicker. Hero.tsx renders one of them; to switch back, change the import
// and the element there (BookSprigEmblem is the previous monochrome version).

const PETAL_ANGLES = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330];

function Book() {
  return (
    <g stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 31c6-3 14-3 19 1 5-4 13-4 19-1v10c-6-3-14-3-19 1-5-4-13-4-19-1Z" fill="currentColor" fillOpacity="0.1" />
      <path d="M24 32v10M9 34.5c4-1 9-.6 12 1.4M9 38c4-1 9-.6 12 1.4M39 34.5c-4-1-9-.6-12 1.4M39 38c-4-1-9-.6-12 1.4" strokeOpacity="0.55" />
    </g>
  );
}

export function BookSprigEmblem() {
  return (
    <svg className="hero-emblem" width="40" height="40" viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <Book />
      <g stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
        <path d="M24 30c-1-6 1-13 0-21" />
        <path d="M24 26c-6 0-10-3-10-8 5 0 9 3 10 8Z" fill="currentColor" fillOpacity="0.22" />
        <path d="M24 21c6 0 10-3 10-8-5 0-9 3-10 8Z" fill="currentColor" fillOpacity="0.22" />
        <path d="M24 16c-5 0-8-2.5-8-6.5 4 0 7 2.5 8 6.5Z" fill="currentColor" fillOpacity="0.22" />
        <path d="M24 10c-2-2-2.5-4.5 0-7 2.5 2.5 2 5 0 7Z" fill="currentColor" fillOpacity="0.35" />
        <path d="M23.5 24.5 17 19.5M24.5 19.5 31 15.5M23.5 14.5 18.5 11.5" strokeOpacity="0.5" strokeWidth="1" />
      </g>
      <g fill="currentColor" fillOpacity="0.55">
        <circle cx="10.5" cy="14" r="1" />
        <circle cx="38" cy="22" r="1.1" />
        <circle cx="13" cy="7.5" r="0.8" />
        <circle cx="35.5" cy="6.5" r="0.9" />
      </g>
    </svg>
  );
}

// A colored sunflower growing from the open book.
export function BookSunflowerEmblem() {
  return (
    <svg className="hero-emblem" width="40" height="40" viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <Book />
      <g strokeLinecap="round" strokeLinejoin="round">
        <path d="M24 20c-.6 4 .6 8 0 11.5" stroke="#3E7D4F" strokeWidth="1.8" />
        <path d="M24 28.5c-5 .2-8-2.5-8-5.500 4.2 0 7.200 2 8 5.500Z" fill="#6DB071" stroke="#3E7D4F" strokeWidth="0.9" />
        <path d="M24 26c4.500 0 7.5-2 7.5-5-4 0-6.800 1.8-7.5 5Z" fill="#6DB071" stroke="#3E7D4F" strokeWidth="0.9" />
      </g>
      <g>
        {PETAL_ANGLES.map((angle) => (
          <ellipse key={angle} cx="24" cy="5" rx="2.7" ry="4.2" transform={`rotate(${angle} 24 11)`} fill="#F4B31B" stroke="#C98A0B" strokeWidth="0.5" />
        ))}
        {PETAL_ANGLES.map((angle) => (
          <ellipse key={`i${angle}`} cx="24" cy="6.2" rx="2.1" ry="3.2" transform={`rotate(${angle + 15} 24 11)`} fill="#FBD34F" stroke="#E0A210" strokeWidth="0.4" />
        ))}
        <circle cx="24" cy="11" r="4.6" fill="#6B4423" stroke="#4A2E16" strokeWidth="0.6" />
        <circle cx="24" cy="11" r="2.6" fill="#4A2E16" />
        <g fill="#9A6A38">
          <circle cx="22.6" cy="9.8" r="0.5" />
          <circle cx="25.4" cy="9.8" r="0.5" />
          <circle cx="24" cy="11.4" r="0.5" />
          <circle cx="22.2" cy="12.4" r="0.45" />
          <circle cx="25.8" cy="12.4" r="0.45" />
        </g>
      </g>
    </svg>
  );
}
