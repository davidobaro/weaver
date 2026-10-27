import {defineConfig} from 'vite'
export default defineConfig({cacheDir:new URL('./.vite',import.meta.url).pathname,esbuild:{jsx:'automatic'}})
