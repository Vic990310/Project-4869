# 1. 基础镜像
FROM python:3.10-slim

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai
# 使用国内镜像源加速浏览器下载
ENV PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/

WORKDIR /app

# 2. 换源、更新并安装所有必要的系统依赖
# GitHub AI 建议的修复：使用 fonts-unifont 替代 ttf-unifont
# 额外修复：安装 Chromium 运行必须的 lib 库，绕过 install-deps 的 bug
# 额外优化：安装 fonts-wqy-zenhei 解决中文乱码
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    git \
    tzdata \
    sudo \
    # --- 字体依赖 ---
    fonts-unifont \
    fonts-ubuntu \
    fonts-noto-color-emoji \
    fonts-wqy-zenhei \
    # --- Chromium 系统依赖 (手动安装以替代 install-deps) ---
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
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    # 清理缓存
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 3. 安装 Python 库
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 4. 仅安装 Chromium 浏览器 (不再运行 install-deps，因为依赖已在上面手动装好)
RUN playwright install chromium && \
    rm -rf /root/.cache/ms-playwright/firefox* && \
    rm -rf /root/.cache/ms-playwright/webkit*

# 5. 复制业务代码
COPY . .
RUN mkdir -p data

# 启动
CMD ["uvicorn", "web_server:app", "--host", "0.0.0.0", "--port", "4869"]