# 1. 基础镜像：锁定 Debian 12 (Bookworm) 稳定版
# 这样 Playwright 的自动脚本就能识别系统并正确安装依赖
FROM python:3.10-slim-bookworm

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

WORKDIR /app

# 2. 安装基础工具
# 安装 sudo 是必须的，因为 playwright install-deps 脚本需要它
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    git \
    tzdata \
    sudo \
    # 安装中文字体 (防止截图/PDF乱码)
    fonts-wqy-zenhei && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 3. 安装 Python 库
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# 4. 全自动安装 Chromium 及其依赖
# (因为换成了 bookworm 稳定版，这个官方脚本终于可以正常工作了)
RUN playwright install-deps chromium && \
    playwright install chromium && \
    # 清理垃圾
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /root/.cache/ms-playwright/firefox* && \
    rm -rf /root/.cache/ms-playwright/webkit*

# 5. 复制业务代码
COPY . .
RUN mkdir -p data

# 启动
CMD ["uvicorn", "web_server:app", "--host", "0.0.0.0", "--port", "4869"]