declare const __WEAVER_VERSION__: string
declare const __WEAVER_BUILT_AT__: string

const build = __WEAVER_BUILT_AT__.replace(/[-:]/g, '').replace('T', '.').slice(0, 15)

export default function BuildVersion() {
  return <small className="build-version" title={`Weaver ${__WEAVER_VERSION__} · Built ${__WEAVER_BUILT_AT__} (UTC)`}
    aria-label={`Weaver version ${__WEAVER_VERSION__}, built ${__WEAVER_BUILT_AT__}`}>
    v{__WEAVER_VERSION__} <span aria-hidden="true">·</span> {build}
  </small>
}
