FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

# 1. 关键修改：加上 DEBIAN_FRONTEND=noninteractive
# 这会让 apt-get 知道它是非交互模式，自动使用默认值，不再弹窗询问
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y tzdata && \
    rm -rf /var/lib/apt/lists/*

# 2. 设置时区 (这一步会覆盖掉默认配置，所以不用担心刚才没选对)
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
