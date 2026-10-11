export default function Logo({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 28 28" aria-hidden="true">
      <rect width="28" height="28" rx="9" fill="#15162e" />
      <path d="M10 8.5v11l9-5.5z" fill="#fff" />
      <path d="M6 21 22 7" stroke="#5eead4" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  )
}
