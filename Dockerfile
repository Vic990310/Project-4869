# 1. 基础镜像
FROM python:3.10-slim

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

WORKDIR /app

# 2. 更新并安装系统依赖 (使用官方源)
# 修复：使用新版字体包名 (fonts-unifont, fonts-ubuntu)
# 保留：手动安装 Chromium 依赖库，避免依赖脚本报错
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    git \
    tzdata \
    sudo \
    # --- 字体依赖 (Debian 12 新名称) ---
    fonts-unifont \
    fonts-ubuntu \
    fonts-noto-color-emoji \
    fonts-wqy-zenhei \
    # --- Chromium 系统依赖 ---
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 && \
    # 设置时区
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    # 清理缓存
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 3. 安装 Python 库 (使用官方 PyPI 源)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. 安装 Chromium 浏览器 (使用官方 CDN)
RUN playwright install chromium && \
    rm -rf /root/.cache/ms-playwright/firefox* && \
    rm -rf /root/.cache/ms-playwright/webkit*

# 5. 复制业务代码
COPY . .
RUN mkdir -p data

# 启动
CMD ["uvicorn", "web_server:app", "--host", "0.0.0.0", "--port", "4869"]