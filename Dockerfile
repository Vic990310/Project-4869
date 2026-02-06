# 1. 改用轻量级 Python 基础镜像 (Debian Bookworm Slim)
FROM python:3.10-slim

# 设置非交互前端，防止安装依赖时弹窗
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

# 设置工作目录
WORKDIR /app

# 2. 替换软件源为阿里云 (可选，加速国内构建) & 安装基础工具
# 注意：安装 Chromium 依赖需要 git 和 curl 等基础工具
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    git \
    tzdata && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    rm -rf /var/lib/apt/lists/*

# 3. 复制并安装 Python 依赖 (包含 playwright 库)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. 【核心瘦身步骤】只安装 Chromium 浏览器和系统依赖
# --with-deps: 自动安装 Chromium 运行所需的 Linux 系统库
# 这里的 chromium 对应代码里的 p.chromium.launch
RUN playwright install chromium --with-deps && \
    # 清理 apt 缓存减小体积
    rm -rf /var/lib/apt/lists/* && \
    # 再次清理可能存在的其他浏览器缓存 (双重保险)
    rm -rf /root/.cache/ms-playwright/firefox* && \
    rm -rf /root/.cache/ms-playwright/webkit*

# 5. 复制业务代码
COPY . .

# 确保数据目录存在
RUN mkdir -p data

# 启动命令
CMD ["uvicorn", "web_server:app", "--host", "0.0.0.0", "--port", "4869"]
