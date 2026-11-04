name: 功能改动
description: 提交一个 Pull Request
body:
  - type: markdown
    attributes:
      value: |
        提 PR 前请确认：本地 `pytest` 与 `cd web-ui && npm run build` 都能过，且 `git status` 里没有 `.env`、`state/`、`data/`。
        详细要求见 [CONTRIBUTING.md](../blob/main/CONTRIBUTING.md)。

  - type: textarea
    id: summary
    attributes:
      label: 这个 PR 做了什么
      description: 一句话说清目的；再列 2-4 条要点。
      placeholder: |
        让候选商品支持「较上次抓取降价」筛选。
        - candidates 接口增加 `price_drop` 参数
        - 卡片显示降幅百分比
        - 补充 3 个单测
    validations:
      required: true

  - type: textarea
    id: scope
    attributes:
      label: 影响范围
      description: 涉及哪些模块、接口、配置项、数据表？是否有不兼容变更？
      placeholder: |
        - 接口：GET /api/workbench/candidates（新增可选参数，向后兼容）
        - 数据：只读 price_snapshots，无迁移
        - 前端：CandidateCard 增加降幅标记
    validations:
      required: true

  - type: textarea
    id: verification
    attributes:
      label: 你如何验证
      placeholder: |
        - pytest 全绿（本地 37 个测试文件）
        - 手动：把两个任务的历史价格造出 10% 降幅，界面正确显示
        - 截图附在下方
    validations:
      required: true

  - type: textarea
    id: traffic
    attributes:
      label: 对请求量 / 成本的影响
      description: 如果动了爬虫或 AI 调用，必须说明。没动就写「无」。
      placeholder: 无（纯查询侧计算）
    validations:
      required: true

  - type: input
    id: issue
    attributes:
      label: 关联 Issue
      placeholder: "Closes #123"

  - type: checkboxes
    id: checklist
    attributes:
      label: 自查清单
      options:
        - label: 没有提交 `.env`、`state/`、`data/`、日志或任何凭据
          required: true
        - label: 新增配置项已同步到 `.env.example` 与 README
          required: true
        - label: 本地 `pytest` 与前端 `npm run build` 均通过
          required: true
        - label: UI 改动已附截图
          required: false
        - label: 我同意以 MIT License 授权本次贡献
          required: true
