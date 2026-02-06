# 1. 基础镜像
FROM python:3.10-slim-bookworm

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai
# 【核心修复】显式指定 Playwright 浏览器路径，确保安装和运行路径一致
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# 2. 安装基础工具
# 【修改】去掉了阿里云加速源 (sed命令)，直接使用 Debian 官方源
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    git \
    tzdata \
    sudo \
    fonts-wqy-zenhei && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 3. 安装 Python 库
COPY requirements.txt .
# 【修改】去掉了 pip 的国内镜像源参数 -i ...
RUN pip install --no-cache-dir -r requirements.txt

# 4. 全自动安装 Chromium
# 注意：因为设置了 ENV PLAYWRIGHT_BROWSERS_PATH，这里会自动安装到 /ms-playwright
RUN playwright install-deps chromium && \
    playwright install chromium && \
    # 清理垃圾
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    # 【修改】清理路径改为 /ms-playwright 下的非 Chromium 浏览器
    rm -rf /ms-playwright/firefox* && \
    rm -rf /ms-playwright/webkit*

# 5. 复制业务代码
COPY . .
RUN mkdir -p data

# 启动
CMD ["uvicorn", "web_server:app", "--host", "0.0.0.0", "--port", "4869"]