export default function WovenThreads() {
  const rows = [10, 20, 30];
  const columns = [10, 20, 30];
  return <svg className="woven-threads" width="31" height="31" viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" aria-hidden="true">
    {columns.map(x => <path key={`warp-${x}`} d={`M${x} 4 C${x - 2} 13 ${x + 2} 27 ${x} 36`} />)}
    {rows.map((y, row) => <g key={`weft-${y}`}>
      {columns.filter((_, column) => (row + column) % 2 === 0).map(x => <path key={x} d={`M${x - 3.5} ${y} H${x + 3.5}`} stroke="var(--weave-background, #eeefe7)" strokeWidth="7" />)}
      {row % 2 === 0
        ? <path d={`M4 ${y} H15.5 M24.5 ${y} H36`} />
        : <path d={`M4 ${y} H5.5 M14.5 ${y} H25.5 M34.5 ${y} H36`} />}
    </g>)}
  </svg>
}
