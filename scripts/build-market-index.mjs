#!/usr/bin/env node
/**
 * 生成 DSH 插件市场索引（market/index.json）。
 *
 * 索引格式见 https://deepseek-harness.github.io/deepseek-harness/guide/plugin-market
 * 用法：
 *   node scripts/build-market-index.mjs
 *   node scripts/build-market-index.mjs --plugin plugins/dsh --output market/index.json
 *
 * 前提：仓库已经 git init 并至少有一次提交（索引要写 commit SHA）。
 */
import { execFileSync } from 'node:child_process'
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(HERE, '..')

function parseArgs(argv) {
  const args = { plugin: 'plugins/dsh', output: 'market/index.json', repoUrl: '', allowPlaceholder: false }
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i]
    if (token === '--plugin') args.plugin = argv[++i]
    else if (token === '--output') args.output = argv[++i]
    else if (token === '--repo-url') args.repoUrl = argv[++i]
    else if (token === '--allow-placeholder') args.allowPlaceholder = true
  }
  return args
}

function git(args, { allowFail = false } = {}) {
  try {
    return execFileSync('git', args, { cwd: REPO_ROOT, encoding: 'utf8' }).trim()
  } catch (error) {
    if (allowFail) return ''
    throw error
  }
}

function toHttpsRepoUrl(raw) {
  const value = String(raw || '').trim()
  if (!value) return ''
  const sshMatch = value.match(/^git@([^:]+):(.+?)(?:\.git)?$/)
  if (sshMatch) return `https://${sshMatch[1]}/${sshMatch[2]}`
  return value.replace(/\.git$/, '')
}

function main() {
  const args = parseArgs(process.argv.slice(2))
  const pluginDir = resolve(REPO_ROOT, args.plugin)
  const pkgPath = join(pluginDir, 'package.json')

  if (!existsSync(pkgPath)) {
    console.error(`✗ 找不到 ${relative(REPO_ROOT, pkgPath)}`)
    process.exit(1)
  }

  const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'))
  if (!pkg.dsh || !pkg.dsh.bundle) {
    console.error(`✗ ${pkg.name} 的 package.json 缺少 dsh.bundle 声明，无法作为组合包上架。`)
    process.exit(1)
  }

  const pluginRel = relative(REPO_ROOT, pluginDir).split('\\').join('/')
  const remoteRaw = args.repoUrl || git(['remote', 'get-url', 'origin'], { allowFail: true })
  const repoUrl = toHttpsRepoUrl(remoteRaw || (pkg.repository && pkg.repository.url) || '')
  const commit = git(['log', '-1', '--format=%H', '--', pluginRel], { allowFail: true })
  const commitTs = git(['log', '-1', '--format=%ct', '--', pluginRel], { allowFail: true })

  if (!repoUrl) {
    console.error('✗ 读不到仓库地址：请先 git remote add origin <url>，或在 package.json 里写 repository.url。')
    process.exit(1)
  }
  if (!/^[0-9a-f]{40}$/.test(commit)) {
    console.error('✗ 读不到插件目录的提交 SHA：请先 git init && git add . && git commit。')
    process.exit(1)
  }
  if (repoUrl.includes('<GITHUB_USER>') && !args.allowPlaceholder) {
    console.error('✗ 仓库地址里还有 <GITHUB_USER> 占位符，请先执行 scripts/replace-placeholders.ps1。')
    console.error('  如果只是想先让仓库里有一份索引（占位符稍后再替换），加 --allow-placeholder。')
    process.exit(1)
  }
  if (repoUrl.includes('<GITHUB_USER>')) {
    console.warn('⚠ 索引里写的是占位符地址，替换占位符后必须重新生成本文件。')
  }

  const iconRel = 'icons/xianyu-monitor.svg'
  const index = {
    format: 1,
    title: {
      en: 'Xianyu Smart Monitor Plugins',
      zh: '闲鱼智能监控插件市场',
    },
    description: {
      en: 'First-party plugins for running the Xianyu smart-monitor service from an agent.',
      zh: '把本机闲鱼智能监控服务的候选商品、任务与运行记录接入 agent 的第一方插件。',
    },
    metadata: {
      categories: {
        productivity: { title: { en: 'Productivity', zh: '效率' } },
        monitoring: { title: { en: 'Monitoring', zh: '监控' } },
      },
      labels: {
        xianyu: { title: { en: 'Xianyu', zh: '闲鱼' } },
        secondhand: { title: { en: 'Second-hand', zh: '二手' } },
        local: { title: { en: 'Local only', zh: '仅本地' } },
      },
      sortKeys: {
        updated: { title: { en: 'Recently updated', zh: '最近更新' }, order: 'desc' },
      },
    },
    plugins: [
      {
        name: pkg.name,
        title: { en: 'Xianyu Smart Monitor', zh: '闲鱼智能监控' },
        description: {
          en: 'Query candidates, tasks and run logs from a locally running Xianyu monitor, and start or stop tasks.',
          zh: '查询本机闲鱼监控的候选商品、任务与运行记录，并可启动/停止任务。需要本机已运行 python -m src.app。',
        },
        icon: iconRel,
        author: pkg.author || '',
        homepage: `${repoUrl}/tree/main/${pluginRel}#readme`,
        repository: { url: repoUrl, directory: pluginRel },
        metadata: {
          category: 'monitoring',
          labels: ['xianyu', 'secondhand', 'local'],
          sortKeys: { updated: Number(commitTs) || 0 },
        },
        versions: [
          {
            version: pkg.version,
            publishTimestamp: Number(commitTs) || Math.floor(Date.now() / 1000),
            source: {
              type: 'git',
              url: repoUrl,
              commit,
              path: pluginRel,
            },
            ...(pkg.engines && pkg.engines.dsh ? { engines: { dsh: pkg.engines.dsh } } : {}),
          },
        ],
      },
    ],
  }

  const outPath = resolve(REPO_ROOT, args.output)
  mkdirSync(dirname(outPath), { recursive: true })
  writeFileSync(outPath, `${JSON.stringify(index, null, 2)}\n`, 'utf8')

  console.log(`✓ 已写入 ${relative(REPO_ROOT, outPath)}`)
  console.log(`  plugin  : ${pkg.name}@${pkg.version}`)
  console.log(`  source  : git ${repoUrl} @ ${commit.slice(0, 7)} (path: ${pluginRel})`)
  console.log(`  发布后   : 把 market/ 目录整体托管到静态站点，索引 URL = <站点>/index.json`)
}

main()
