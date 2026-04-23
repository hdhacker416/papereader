# Paper Reader / 论文阅读助手

Paper Reader is a local AI-powered paper reading and research workspace. It can create reading tasks from paper titles, search and download PDFs from arXiv/OpenReview, chat with papers, manage notes and collections, and run a conference-pack-based deep research workflow.
Paper Reader 是一个本地 AI 驱动的论文阅读与研究工作台。它可以从论文标题创建阅读任务，自动从 arXiv/OpenReview 搜索并下载 PDF，与论文对话，管理笔记和收藏夹，并提供基于 conference packs 的 Deep Research 工作流。

<p align="center">
  <img src="assets/main.png" width="36%" alt="Main Interface" />
  <img src="assets/library.png" width="61%" alt="Library Interface" />
</p>

### Video Showcase / 视频展示
[Watch the demo video / 观看演示视频](https://www.bilibili.com/video/BV1gNNuzzEWJ/?spm_id_from=333.1387.homepage.video_card.click&vd_source=910a83c9601312e34c7ebcf4051f6ad2)

## Features / 功能特性

- **Task-based reading pipeline / 任务式阅读流程**: Create tasks, batch add paper titles, process papers in the background, and retry or reread papers with updated prompts and models.
- **Automatic paper discovery / 自动检索论文**: Resolve paper sources from existing links or search arXiv and OpenReview, then download PDFs into local storage.
- **Multi-model reading / 多模型阅读**: Use Gemini models and Qwen-family models for paper interpretation, chat, reread, and report generation.
- **Reading Room / 阅读室**: Read PDFs, continue paper-grounded chat, save notes, and add papers into collections from one place.
- **Prompt templates / 提示词模板**: Maintain reusable reading templates, select a default template, and override prompts per task.
- **Collections / 收藏夹**: Organize papers into nested collections and rerun reading over a whole collection.
- **Deep Research / 深度研究**: Search conference packs, select papers into a task, auto-create research tasks, and generate task-level synthesis reports.
- **Research pack workflow / Research Pack 工作流**: Install prebuilt packs from GitHub Releases, inspect local packs, build new packs, and optionally upload them back to GitHub Releases.
- **Local-first storage / 本地优先存储**: Database, PDFs, notes, chat history, and packs stay on your machine under the project directory.

## Current Architecture / 当前项目结构

- `backend/`: FastAPI application, SQLite models, background paper processor, report generation, and Deep Research APIs.
- `frontend/`: React + TypeScript + Vite UI for tasks, reader, templates, collections, and research workflows.
- `research/`: Standalone retrieval, rerank, pack-building, and deep research pipeline modules used by the backend.
- `data/`: Auto-created runtime data directory. Stores `app.db`, downloaded PDFs, and local research assets.
- `start.py`: Launcher script that starts both backend and frontend and prints the final URLs.

## Requirements / 环境要求

- Python 3.10+ recommended
- Node.js and npm available in `PATH`
- A local environment that can run both Python and Node processes

The codebase supports several workflows, and the required API keys depend on which features you use.
当前仓库支持多条工作流，不同功能需要的 API Key 不完全相同。

## Environment Variables / 环境变量

Create `backend/.env` or export the variables in your shell.
推荐直接创建 `backend/.env` 文件，也可以在 shell 环境中导出这些变量。

| Variable | Required | Used for |
| --- | --- | --- |
| `GEMINI_API_KEY` | Required for Gemini-based reading and reports | Gemini paper interpretation, paper chat, task report generation, parts of Deep Research |
| `DASHSCOPE_API_KEY` | Required for Qwen and Deep Research | Qwen models, DashScope embeddings, rerank, pack build, research self-check |
| `DASHSCOPE_BASE_URL` | Optional | Override the DashScope OpenAI-compatible endpoint |
| `GITHUB_TOKEN` | Optional | Upload research packs to GitHub Releases |

Example `backend/.env`:

```dotenv
GEMINI_API_KEY=your_gemini_api_key_here
DASHSCOPE_API_KEY=your_dashscope_api_key_here
# DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
# GITHUB_TOKEN=ghp_xxx
```

You can also copy the example file first:

```bash
cp backend/.env.example backend/.env
```

## Installation / 安装

[Watch the installation tutorial / 观看安装教程](https://www.bilibili.com/video/BV1gNNuzzEpZ/?spm_id_from=333.1387.homepage.video_card.click)

### 1. Clone the repository / 克隆仓库

```bash
git clone https://github.com/hdhacker416/papereader.git
cd papereader
```

### 2. Create a Python environment / 创建 Python 环境

You can use `venv`, Conda, or your preferred environment manager.
可以使用 `venv`、Conda，或你习惯的 Python 环境管理方式。

Example with `venv`:

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install backend dependencies / 安装后端依赖

```bash
pip install -r backend/requirements.txt
```

### 4. Install frontend dependencies / 安装前端依赖

```bash
cd frontend
npm install
cd ..
```

### 5. Configure API keys / 配置 API Key

Create `backend/.env` and fill in the variables you need for your workflow.
创建 `backend/.env`，按你要使用的功能填写对应变量。

## Running the Application / 运行应用

Run the launcher from the repository root:
请在仓库根目录执行启动脚本：

```bash
python start.py
```

What `start.py` does:

- Starts the FastAPI backend and the Vite frontend together
- Uses `backend/requirements.txt` as the backend dependency reference
- Runs `npm install` automatically if `frontend/node_modules` is missing
- Loads environment variables from `backend/.env` during startup
- Automatically picks the next available ports if `8000` or `5173` is already occupied

By default, the URLs are:

- Frontend: `http://localhost:5173`
- Backend docs: `http://localhost:8000/docs`

If one of those ports is already in use, `start.py` will print the actual ports it selected. Use the printed URLs rather than assuming `5173` and `8000`.
如果默认端口被占用，`start.py` 会自动切到其他可用端口。请以终端里打印出的实际地址为准。

## Typical Workflows / 常见工作流

### Basic paper reading / 基础论文阅读

1. Start the app with `python start.py`.
2. Open the frontend URL printed in the terminal.
3. Create a task in `Tasks`.
4. Add paper titles and let the backend resolve sources and download PDFs.
5. Open a paper in the Reading Room to chat, read notes, and manage collections.

### Deep Research / 深度研究

1. Open the `Research` page.
2. Run the self-check to confirm API keys and local assets are ready.
3. Install existing research packs from Releases, or build packs locally.
4. Search the conference packs, select papers, and create a reading task.
5. Generate a task-level report after enough papers have been interpreted.

## Project Structure / 项目结构

```text
papereader/
  backend/            FastAPI backend and background services
  frontend/           React + TypeScript + Vite frontend
  research/           Retrieval, rerank, pack, and Deep Research modules
  data/               Local runtime data (database, PDFs, packs, caches)
  assets/             README images and other static assets
  start.py            One-command launcher for backend + frontend
```

## Troubleshooting / 故障排除

- **`GEMINI_API_KEY` missing**: Gemini-based reading, reports, and some research flows will fail until the key is configured.
- **`DASHSCOPE_API_KEY` missing**: Qwen models and Deep Research retrieval/rerank workflows will fail until the key is configured.
- **Frontend does not start**: Confirm `node` and `npm` are available in `PATH`, then rerun `npm install` inside `frontend/`.
- **Ports already in use**: This is usually fine. `start.py` will choose a free backend/frontend port and print the actual URLs.
- **Research page says there are no searchable assets**: Install a pack from Releases or build packs locally before running conference search.
- **Pack upload fails**: Configure `GITHUB_TOKEN` on the backend side before using the upload flow.

## Notes / 备注

- Paper PDFs are stored under `data/pdfs/`.
- The SQLite database is stored at `data/app.db`.
- The backend performs lightweight backward-compatible schema migration checks on startup.
- `research/README.md` documents the internal Deep Research module design in more detail.
