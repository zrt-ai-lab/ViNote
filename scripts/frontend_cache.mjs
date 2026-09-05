import { createHash } from 'node:crypto'
import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const web = join(root, 'web')
const output = join(root, 'static-build')
const dependencyStamp = join(web, 'node_modules', '.vinote-install.json')
const buildStamp = join(output, '.vinote-build.json')

/** Hash file contents, not mtimes, so restored checkouts invalidate correctly. */
function fingerprint(paths) {
  const hash = createHash('sha256')
  for (const path of paths.sort()) {
    hash.update(path.replace(root, '')).update(readFileSync(path))
  }
  return hash.digest('hex')
}

/** Enumerate controlled input directories; cache stamps never hash themselves. */
function filesIn(directory) {
  if (!existsSync(directory)) return []
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name)
    if (path === buildStamp) return []
    return entry.isDirectory() ? filesIn(path) : entry.isFile() ? [path] : []
  })
}

function readStamp(path) {
  try { return JSON.parse(readFileSync(path, 'utf8')) } catch { return null }
}

function dependencyKey() {
  return `${process.version}/${process.platform}/${process.arch}/${fingerprint([
    join(web, 'package.json'), join(web, 'package-lock.json'),
  ])}`
}

function buildKey() {
  const configFiles = readdirSync(web).filter(name =>
    /^(?:index\.html|package(?:-lock)?\.json|(?:vite|tsconfig|postcss|tailwind)\..+)$/.test(name),
  ).map(name => join(web, name))
  return `${dependencyKey()}/${fingerprint([
    ...filesIn(join(web, 'src')), ...filesIn(join(web, 'public')), ...configFiles,
  ])}`
}

function dependenciesReady() {
  return ['vite', 'typescript', 'react', 'react-dom'].every(name =>
    existsSync(join(web, 'node_modules', name, 'package.json')),
  ) && readStamp(dependencyStamp)?.key === dependencyKey()
}

function buildReady() {
  const stamp = readStamp(buildStamp)
  return existsSync(join(output, 'index.html')) && stamp?.key === buildKey()
    && stamp?.output === fingerprint(filesIn(output))
}

try {
  switch (process.argv[2]) {
    case 'check-deps': process.exitCode = dependenciesReady() ? 0 : 1; break
    case 'check-build': process.exitCode = buildReady() ? 0 : 1; break
    case 'mark-deps': writeFileSync(dependencyStamp, JSON.stringify({ key: dependencyKey() })); break
    case 'mark-build': writeFileSync(buildStamp, JSON.stringify({ key: buildKey(), output: fingerprint(filesIn(output)) })); break
    default: throw new Error('Expected check-deps, check-build, mark-deps or mark-build')
  }
} catch (error) {
  console.error(`Frontend cache: ${error.message}`)
  process.exitCode = 1
}
