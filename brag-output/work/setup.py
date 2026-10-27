from pathlib import Path
p=Path('brag-output/work/src/App.tsx');s=p.read_text()
s=s.replace('useState<State | null>(null)', 'useState<State | null>((window as any).__film.data)')
s=s.replace("() => window.location.hash === '#for-you' ? 'for-you' : window.location.hash === '#people' ? 'people' : 'notes'", '() => (window as any).__film.view')
s=s.replace('useState(readDraft)', 'useState(() => (window as any).__film.draft)')
s=s.replace('useState<number | null>(0)', 'useState<number | null>((window as any).__film.personId)');p.write_text(s)
p=Path('brag-output/work/src/ForYou.tsx');s=p.read_text().replace('useState<Feed | null>(null)', 'useState<Feed | null>((window as any).__film.feed)');p.write_text(s)
Path('brag-output/work/src/api.ts').write_text("export class ApiError extends Error { constructor(message:string, public noteId?:number){super(message)} }\nexport async function api<T>(path:string,method='GET',body?:unknown):Promise<T>{return new Promise(()=>{})}\n")
