/** Shared page introduction keeps each workspace view on the same typographic baseline. */
export default function PageHeading({ title, subtitle }: { title: string; subtitle: string }) {
  return <div className="page-heading"><div><h1>{title}</h1><p className="subtitle">{subtitle}</p></div></div>
}
