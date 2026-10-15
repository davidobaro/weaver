export default function WovenThreads() {
  // Alternating gaps in the horizontal strands reveal the vertical strands below.
  const rows = [10, 20, 30];
  const columns = [10, 20, 30];
  return <svg className="woven-threads" width="31" height="31" viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" aria-hidden="true">
    {columns.map(x => <path key={`warp-${x}`} d={`M${x} 4 C${x - 2} 13 ${x + 2} 27 ${x} 36`} />)}
    {rows.map((y, row) => <g key={`weft-${y}`}>
      {/* Short background cuts give each crossing a clear over-and-under order. */}
      {columns.filter((_, column) => (row + column) % 2 === 0).map(x => <path key={x} d={`M${x - 3.5} ${y} H${x + 3.5}`} stroke="var(--weave-background, #eeefe7)" strokeWidth="6" />)}
      {row % 2 === 0
        ? <path d={`M4 ${y} H16.5 M23.5 ${y} H36`} />
        : <path d={`M4 ${y} H6.5 M13.5 ${y} H26.5 M33.5 ${y} H36`} />}
    </g>)}
  </svg>
}
