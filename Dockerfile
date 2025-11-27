# 1. 使用官方 Python 镜像作为基础
FROM python:3.11-slim

# 2. 设置时区和工作目录
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
WORKDIR /app

# 3. 安装最新版 uv
RUN pip install -U uv

# 4. 复制依赖文件
COPY pyproject.toml uv.lock ./

# 5. 使用 uv 安装项目及其依赖到系统环境
RUN uv pip install --system .

# 6. 复制所有项目文件到工作目录
COPY . .

# 7. 暴露 FastAPI 运行的端口
EXPOSE 8000

# 8. 启动应用的命令
# 使用 uvicorn 启动 FastAPI 应用，监听所有网络接口
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]