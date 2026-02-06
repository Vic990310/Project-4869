# 1. 基础镜像
FROM python:3.10-slim

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

WORKDIR /app

# 2. 安装基础工具 (关键修正：增加了 sudo，且暂时不清理 apt 缓存)
# Playwright 的 --with-deps 脚本需要 sudo 权限和 apt 索引才能运行
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    git \
    tzdata \
    sudo && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 3. 安装 Python 库
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. 安装 Chromium 及系统依赖 (关键步骤)
# 这里会调用 sudo apt-get install，所以必须在上一步保留 apt 缓存
RUN playwright install chromium --with-deps && \
    # 所有的装完了，现在才是清理垃圾的时候
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    # 删除多余的浏览器 (Firefox/Webkit)
    rm -rf /root/.cache/ms-playwright/firefox* && \
    rm -rf /root/.cache/ms-playwright/webkit*

# 5. 复制代码
COPY . .
RUN mkdir -p data

# 启动
CMD ["uvicorn", "web_server:app", "--host", "0.0.0.0", "--port", "4869"]