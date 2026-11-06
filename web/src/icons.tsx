/** The few icons the UI needs, drawn on one 16px grid. */

const paths = {
  play: <path d="M4.5 2.8v10.4L13 8 4.5 2.8Z" fill="currentColor" stroke="none" />,
  pause: (
    <>
      <rect x="4" y="3" width="3" height="10" rx="1" fill="currentColor" stroke="none" />
      <rect x="9" y="3" width="3" height="10" rx="1" fill="currentColor" stroke="none" />
    </>
  ),
  stop: <rect x="4" y="4" width="8" height="8" rx="1.5" fill="currentColor" stroke="none" />,
  left: <path d="M10 3 5 8l5 5" />,
  right: <path d="m6 3 5 5-5 5" />,
  send: <path d="M8 13V3M3.5 7.5 8 3l4.5 4.5" />,
  close: <path d="m4 4 8 8M12 4l-8 8" />,
  pin: (
    <>
      <path d="M8 14.5s5-4.6 5-8.5a5 5 0 0 0-10 0c0 3.9 5 8.5 5 8.5Z" />
      <circle cx="8" cy="6" r="1.6" />
    </>
  ),
  route: (
    <>
      <circle cx="3.5" cy="12.5" r="1.8" />
      <circle cx="12.5" cy="3.5" r="1.8" />
      <path d="M5.3 12.5H10a2.5 2.5 0 0 0 0-5H6a2.5 2.5 0 0 1 0-5h4.7" />
    </>
  ),
  message: <path d="M2.5 4.5a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2H7l-3 2.5v-2.5a2 2 0 0 1-1.5-2v-5Z" />,
  photo: (
    <>
      <rect x="2" y="3" width="12" height="10" rx="2" />
      <circle cx="5.7" cy="6.5" r="1" />
      <path d="m2.5 11.5 3-3 2.5 2.5 2-2 3.5 3" />
    </>
  ),
  globe: (
    <>
      <circle cx="8" cy="8" r="6" />
      <path d="M2 8h12M8 2c2 2 2.6 4 2.6 6S10 12 8 14C6 12 5.4 10 5.4 8S6 4 8 2Z" />
    </>
  ),
  calendar: (
    <>
      <rect x="2.5" y="3.5" width="11" height="10" rx="2" />
      <path d="M2.5 7h11M5.5 2v3M10.5 2v3" />
    </>
  ),
  note: <path d="M4 2.5h5.5L12.5 5.5v8H4a.5.5 0 0 1-.5-.5V3a.5.5 0 0 1 .5-.5ZM9.5 2.5v3h3M6 8.5h4M6 11h3" />,
  music: (
    <>
      <path d="M6 12V3.5l7-1.5V10.5" />
      <circle cx="4.3" cy="12" r="1.7" />
      <circle cx="11.3" cy="10.5" r="1.7" />
    </>
  ),
  receipt: <path d="M3.5 2v12l1.5-1 1.5 1L8 13l1.5 1 1.5-1 1.5 1V2l-1.5 1-1.5-1L8 3 6.5 2 5 3 3.5 2ZM6 6.5h4M6 9.5h4" />,
  card: (
    <>
      <rect x="2" y="3.5" width="12" height="9" rx="2" />
      <path d="M2 6.8h12M4.5 10h2" />
    </>
  ),
  commit: (
    <>
      <circle cx="8" cy="8" r="2.5" />
      <path d="M1.5 8h4M10.5 8h4" />
    </>
  ),
  app: (
    <>
      <rect x="2.5" y="2.5" width="4.5" height="4.5" rx="1.2" />
      <rect x="9" y="2.5" width="4.5" height="4.5" rx="1.2" />
      <rect x="2.5" y="9" width="4.5" height="4.5" rx="1.2" />
      <rect x="9" y="9" width="4.5" height="4.5" rx="1.2" />
    </>
  ),
  heart: <path d="M8 13.5S2.5 10.3 2.5 6.3A3 3 0 0 1 8 4.7a3 3 0 0 1 5.5 1.6c0 4-5.5 7.2-5.5 7.2Z" />,
  ticket: <path d="M2.5 4.5h11v2.3a1.2 1.2 0 0 0 0 2.4v2.3h-11V9.2a1.2 1.2 0 0 0 0-2.4V4.5ZM9.5 4.5v7" />,
  dot: <circle cx="8" cy="8" r="2.5" />,
  panel: (
    <>
      <rect x="2" y="3" width="12" height="10" rx="2" />
      <path d="M10 3v10" />
    </>
  ),
};

export type IconName = keyof typeof paths;

export function Icon({ name }: { name: IconName }) {
  return (
    <svg
      className="icon"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}
