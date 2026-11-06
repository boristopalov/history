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
  panel: (
    <>
      <rect x="2" y="3" width="12" height="10" rx="2" />
      <path d="M10 3v10" />
    </>
  ),
};

export function Icon({ name }: { name: keyof typeof paths }) {
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
