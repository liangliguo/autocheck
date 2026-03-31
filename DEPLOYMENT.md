# AutoCheck 公网部署指南

本项目通过 GitHub Actions 自动构建 Docker 镜像并发布到 GitHub Container Registry (GHCR)，你可以在任何支持 Docker 的服务器上运行。

## 方案概述

- ✅ **完全使用 GitHub 功能**：GitHub Actions + GitHub Container Registry
- ✅ **自动化**：推送代码后自动构建镜像
- ✅ **免费**：GHCR 对公开仓库完全免费

## 一、自动构建 Docker 镜像

### 1. 启用 GitHub Actions

推送代码后，GitHub Actions 会自动：
1. 构建 Docker 镜像
2. 推送到 GitHub Container Registry
3. 镜像地址：`ghcr.io/liangliguo/autocheck:fix-api-compatibility`

### 2. 查看构建状态

访问你的仓库 → Actions 标签页，查看构建进度

## 二、在云服务器部署

### 方案 A：在你自己的服务器上运行

```bash
# 1. 安装 Docker（如果还没有）
curl -fsSL https://get.docker.com | sh

# 2. 登录 GitHub Container Registry（如果镜像是私有的）
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# 3. 拉取镜像
docker pull ghcr.io/liangliguo/autocheck:fix-api-compatibility

# 4. 运行容器
docker run -d \
  --name autocheck \
  -p 8000:8000 \
  -e OPENAI_API_KEY="sk-你的密钥" \
  -e AUTOCHECK_OPENAI_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1" \
  -e AUTOCHECK_CHAT_MODEL="qwen-max" \
  -e AUTOCHECK_VERIFY_MODEL="qwen-max" \
  -e AUTOCHECK_TEMPERATURE="0" \
  -e AUTOCHECK_ENABLE_LLM_EXTRACTION="false" \
  -e AUTOCHECK_ENABLE_LLM_VERIFICATION="true" \
  -e AUTOCHECK_STRUCTURED_OUTPUT_METHOD="function_calling" \
  ghcr.io/liangliguo/autocheck:fix-api-compatibility

# 5. 查看日志
docker logs -f autocheck
```

访问 `http://你的服务器IP:8000`

### 方案 B：使用免费云服务（推荐）

#### 1. Railway.app（最简单）

1. 访问 https://railway.app/
2. 使用 GitHub 账号登录
3. 点击 "New Project" → "Deploy from GitHub repo"
4. 选择 `liangliguo/autocheck` 仓库
5. 选择 `fix/api-compatibility` 分支
6. Railway 会自动检测 Dockerfile 并构建
7. 在 "Variables" 标签页添加环境变量：
   - `OPENAI_API_KEY`
   - `AUTOCHECK_OPENAI_BASE_URL`
   - `AUTOCHECK_CHAT_MODEL=qwen-max`
   - 其他配置...
8. 部署完成后会获得一个公网地址（如 `https://autocheck.railway.app`）

**优点**：
- 免费额度 $5/月
- 自动从 GitHub 部署
- 提供 HTTPS 和公网域名

#### 2. Render.com（完全免费）

1. 访问 https://render.com/
2. 使用 GitHub 账号登录
3. 点击 "New +" → "Web Service"
4. 连接你的 GitHub 仓库
5. 选择 `fix/api-compatibility` 分支
6. Render 自动检测 Dockerfile
7. 添加环境变量（同上）
8. 点击 "Create Web Service"

**优点**：
- 完全免费（Free tier）
- 自动 HTTPS 证书
- 自动从 GitHub 部署

#### 3. Fly.io

```bash
# 1. 安装 flyctl
curl -L https://fly.io/install.sh | sh

# 2. 登录
flyctl auth login

# 3. 在项目目录初始化
cd /path/to/autocheck
flyctl launch

# 4. 设置环境变量
flyctl secrets set OPENAI_API_KEY="sk-你的密钥"
flyctl secrets set AUTOCHECK_OPENAI_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
flyctl secrets set AUTOCHECK_CHAT_MODEL="qwen-max"
flyctl secrets set AUTOCHECK_VERIFY_MODEL="qwen-max"

# 5. 部署
flyctl deploy
```

## 三、配置域名（可选）

如果你有自己的域名，可以在云服务商的设置中绑定自定义域名。

## 四、更新部署

当你推送新代码到 GitHub 后：

- **Railway/Render**：会自动重新部署
- **自己的服务器**：
  ```bash
  docker pull ghcr.io/liangliguo/autocheck:fix-api-compatibility
  docker stop autocheck
  docker rm autocheck
  # 重新运行 docker run 命令
  ```

## 注意事项

1. **API Key 安全**：不要将 API Key 写入代码，使用环境变量
2. **免费额度**：注意云服务的免费额度限制
3. **数据持久化**：如需保存数据，需要配置 Docker volume
4. **监控**：建议使用 UptimeRobot 等服务监控在线状态

## 推荐方案对比

| 方案 | 难度 | 费用 | 域名 | 自动部署 |
|------|------|------|------|----------|
| Railway.app | ⭐ | $5/月免费额度 | ✅ | ✅ |
| Render.com | ⭐ | 完全免费 | ✅ | ✅ |
| Fly.io | ⭐⭐ | 免费额度 | ✅ | ✅ |
| 自己服务器 | ⭐⭐⭐ | 服务器费用 | 需配置 | 需手动 |

**新手推荐**：Railway.app 或 Render.com
