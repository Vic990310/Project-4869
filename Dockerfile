FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

# Set timezone
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure data directory exists
RUN mkdir -p data

# Default command (can be overridden)
CMD ["uvicorn", "web_server:app", "--host", "0.0.0.0", "--port", "4869"]
