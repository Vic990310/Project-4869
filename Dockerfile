FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

# 1. 先安装 tzdata (关键修复步骤)
# 必须先更新源并安装 tzdata，否则 /usr/share/zoneinfo 目录可能不存在
RUN apt-get update && apt-get install -y tzdata && rm -rf /var/lib/apt/lists/*

# 2. 然后再设置时区
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure data directory exists
RUN mkdir -p data

# Default command
CMD ["uvicorn", "web_server:app", "--host", "0.0.0.0", "--port", "4869"]
