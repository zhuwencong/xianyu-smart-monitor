#!/usr/bin/env node
/**
 * 检查三处版本号是否一致：
 *   1. plugins/dsh/package.json         → version
 *   2. plugins/workbuddy/<skill>/SKILL.md → frontmatter version
 *   3. market/index.json                → 对应插件的 versions[0].version
 *
 * 用法：node scripts/check-plugin-versions.mjs
 */
import { readFileSync, existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(HERE, '..')

function readSkillVersion(path) {
  if (!existsSync(path)) return { error: `找不到 ${path}` }
  const content = readFileSync(path, 'utf8')
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---/)
  if (!match) return { error: `${path} 缺少 YAML frontmatter` }
  const versionLine = match[1]
    .split(/\r?\n/)
    .find((line) => /^version\s*:/.test(line.trim()))
  if (!versionLine) return { error: `${path} 的 frontmatter 缺少 version` }
  return { version: versionLine.split(':', 2)[1].trim().replace(/^["']|["']$/g, '') }
}

function main() {
  const problems = []

  const pkgPath = join(REPO_ROOT, 'plugins', 'dsh', 'package.json')
  if (!existsSync(pkgPath)) {
    console.error('✗ 找不到 plugins/dsh/package.json')
    process.exit(1)
  }
  const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'))
  const dshVersion = pkg.version

  const skillDir = join(REPO_ROOT, 'plugins', 'workbuddy', 'xianyu-monitor')
  const skillVersion = readSkillVersion(join(skillDir, 'SKILL.md'))

  let marketVersion = null
  const marketPath = join(REPO_ROOT, 'market', 'index.json')
  if (existsSync(marketPath)) {
    const index = JSON.parse(readFileSync(marketPath, 'utf8'))
    const entry = (index.plugins || []).find((plugin) => plugin.name === pkg.name)
    if (!entry) problems.push(`market/index.json 里没有 ${pkg.name}`)
    else if (!entry.versions || entry.versions.length === 0) {
      problems.push(`market/index.json 里 ${pkg.name} 没有版本`)
    } else {
      marketVersion = entry.versions[0].version
    }
  } else {
    problems.push('market/index.json 不存在（先跑 node scripts/build-market-index.mjs）')
  }

  if (skillVersion.error) problems.push(skillVersion.error)

  const rows = [
    ['plugins/dsh/package.json', dshVersion],
    ['plugins/workbuddy/xianyu-monitor/SKILL.md', skillVersion.version ?? '(未读到)'],
    ['market/index.json', marketVersion ?? '(未读到)'],
  ]
  const width = Math.max(...rows.map(([name]) => name.length))
  for (const [name, version] of rows) {
    console.log(`  ${name.padEnd(width)}  ${version}`)
  }

  const distinct = new Set(rows.map(([, version]) => version).filter(Boolean))
  if (distinct.size > 1) {
    problems.push(`版本号不一致：${[...distinct].join(' / ')}`)
  }

  if (problems.length > 0) {
    console.error('\n✗ 版本检查未通过：')
    for (const problem of problems) console.error(`  - ${problem}`)
    process.exit(1)
  }

  console.log(`\n✓ 三处版本一致：${dshVersion}`)
}

main()
