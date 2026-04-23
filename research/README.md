# Research Module

## 目标

`research/` 是独立于当前 Web 后端框架的研究流水线模块。

它只负责 Deep Research 本身的逻辑，不负责：

- FastAPI 路由
- 前端页面
- ORM 数据表操作
- 任务页状态管理

这些接入工作应由 `backend/` 负责，`backend/` 通过 adapter 调用 `research/`。

## 设计原则

- 研究逻辑与应用框架解耦
- 粗排和精排尽量不用贵模型
- 贵模型只用于精读和最终报告
- PDF 下载按需进行，不做一上来的全量预下载
- 所有中间产物尽量结构化，便于缓存、调试和复用

## 核心流程

当前流程确定为 5 步：

### 1. 语料准备

目标：

- 从固定 GitHub repo 更新 `paperlists`
- 读取会议论文 metadata
- 做字段规范化
- 做去重和基础清洗
- 生成统一语料格式
- 为后续检索建立基础索引

输入：

- GitHub 上游 `paperlists` repo
- 本地同步后的 `paperlists/<conference>/<year>.json`

输出：

- normalized paper records
- corpus manifest
- retrieval-ready metadata store

说明：

- 这一步不是全量下载 PDF
- 第一版优先围绕 metadata 建立可检索语料
- 第一版只抽取所有会议基本稳定存在的最小公共字段

### 2. 粗排

目标：

- 根据 query 从全量 metadata 中高召回找出候选集

建议方案：

- embedding retrieval
- 可选 BM25 或 hybrid retrieval

输入：

- query
- normalized corpus
- retrieval index

输出：

- top 100 到 300 候选论文

要求：

- 优先保证召回率
- 不在这一层做过多复杂判断

### 3. 精排

目标：

- 对粗排候选进一步排序
- 压缩成较小 shortlist

建议方案：

- reranker
- 轻量级开源排序模型

输入：

- query
- retrieved candidates

输出：

- top 20 到 50 shortlist

要求：

- 重点提升精度
- 保留打分和排序理由的结构化结果

### 4. 精读

目标：

- 对 shortlist 进行全文级分析

包括：

- 按需下载 PDF
- PDF 解析和分块
- 逐篇结构化阅读
- 生成 per-paper brief 和 research note

输入：

- query
- shortlist

输出：

- paper brief
- research note
- optional parsing cache

建议策略：

- top 30 到 50 做轻读
- top 10 到 15 做深读

说明：

- PDF 下载放在这一步，不放在最前面
- 单篇下载失败要可容错，不能让整个 job 崩掉

### 5. 报告生成

目标：

- 将逐篇分析结果聚合为最终 research report

输出报告至少应回答：

- 这个问题现在的研究格局是什么
- 哪些方向已经解决
- 哪些关键缺口还存在
- 值得做的 project ideas 是什么

输入：

- query
- structured analysis results

输出：

- final structured report

说明：

- 报告应基于结构化精读结果，而不是直接基于原始 PDF 文本

## 推荐目录

第一版建议逐步扩展到如下结构：

```text
research/
  README.md
  __init__.py
  config.py
  types.py
  corpus/
  retrieval/
  rerank/
  reader/
  report/
  pipeline/
  storage/
  providers/
```

各层职责建议如下：

- `corpus/`
  - 读取 paperlists
  - 规范化和去重
  - 生成统一语料对象

- `retrieval/`
  - embedding 编码
  - 索引构建
  - query 召回

- `rerank/`
  - 对粗排候选做二次排序

- `reader/`
  - PDF 下载
  - PDF 解析
  - chunk 构建
  - 精读分析

- `report/`
  - 跨论文聚合
  - 最终报告生成

- `pipeline/`
  - 把 5 步串起来
  - 提供统一入口

- `storage/`
  - 本地中间产物缓存
  - pack、manifest、cache 管理

- `providers/`
  - 模型调用封装
  - embedding、reranker、LLM provider 适配

## 与 Backend 的边界

`research/` 不应直接依赖：

- `backend/models.py`
- FastAPI request/response 对象
- 当前数据库 session

推荐边界：

- `research/` 定义自己的数据结构和流水线接口
- `backend/` 负责把 HTTP 请求转换为 `research/` 输入
- `backend/` 负责保存结果、管理 job 状态、向前端返回数据

## 离线与在线

当前模块实际分为两部分：

- 离线构建部分
  - 运行在 GPU 机器
  - 低频执行
  - 从 GitHub 更新 `paperlists`
  - 生成 normalized corpus、embedding、index、pack

- 在线运行部分
  - 运行在普通设备
  - 实时响应 user query
  - 下载并加载已构建好的会议 pack
  - 执行 coarse retrieval、rerank、deep read、report

## 第一版实现优先级

建议按以下顺序开发：

1. metadata 语料准备
2. 粗排 retrieval
3. pack 构建与分发

## Pack Distribution

第一版分发机制采用 `conference/year` 级别的 zip 包。

- 构建侧把标准化语料、embedding 和 manifest 打成一个 pack
- 推荐先发布到 GitHub Releases
- 使用侧只需要下载 zip 并安装到本地 `installed_packs`

pack 内容结构：

```text
manifest.json
normalized/<conference><year>.jsonl
embeddings/<conference><year>.embeddings.json
metadata/<conference><year>.manifest.json
```

构建 pack：

```bash
python -m research.build.build_packs --conferences iclr nips --years 2025 --version v1
```

安装本地或远程 pack：

```bash
python -m research.runtime.install_pack /path/to/iclr-2025-v1.zip
python -m research.runtime.install_pack https://github.com/<owner>/<repo>/releases/download/<tag>/iclr-2025-v1.zip
```
3. 精排 rerank
4. 精读 analyze
5. final report

不要第一版就优先做：

- 全量 PDF 下载
- 所有会议年份一次性打包
- 与前端深度耦合的接口逻辑

## 第一版最小闭环

第一版至少跑通这个链路：

1. 读取一个会议年份的 paperlist
2. 根据 query 返回 shortlist
3. 对 shortlist 做按需 PDF 精读
4. 输出结构化 per-paper 结果
5. 生成 final report

## 当前结论

这份模块设计已经确定：

- `research/` 单独放目录
- `research/` 专注研究逻辑
- `backend/` 负责框架接入
- 流程按 5 步实现
- PDF 下载后移到精读阶段
