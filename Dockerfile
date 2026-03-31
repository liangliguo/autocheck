FROM python:3.12-slim

WORKDIR /app

# 安装 uv
RUN pip install uv

# 复制项目文件
COPY pyproject.toml uv.lock ./
COPY src ./src

# 安装依赖
RUN uv sync --no-dev

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uv", "run", "autocheck", "web", "--host", "0.0.0.0", "--port", "8000"]
