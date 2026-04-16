#!/bin/bash

# ============================================================
# 启动脚本 - 支持多种部署模式
# ============================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

usage() {
    echo "用法: $0 [模式]"
    echo ""
    echo "模式:"
    echo "  dev        开发模式 (单进程 + MemorySaver)"
    echo "  prod       生产模式 (多 Worker + Redis + vLLM 集群)"
    echo "  vllm       启动 vLLM 集群 (需要 GPU)"
    echo "  api        启动 API 服务 (依赖 Redis 和 vLLM)"
    echo "  all        启动所有服务 (完整生产环境)"
    echo ""
    echo "示例:"
    echo "  $0 dev              # 开发模式"
    echo "  $0 all              # 完整生产环境"
}

# 开发模式 - 单进程
start_dev() {
    echo -e "${GREEN}[启动开发模式]${NC}"
    echo "  - 单进程 + asyncio"
    echo "  - MemorySaver (内存状态)"
    echo "  - OpenAI API"

    export CHECKPOINTER_TYPE=memory
    export LLM_PROVIDER=openai

    poetry run python -m uvicorn customer_support_chat.app.api:app --reload --port 8000
}

# 生产模式 - 多 Worker + Redis
start_prod() {
    echo -e "${GREEN}[启动生产模式]${NC}"
    echo "  - 多 Worker + Redis 共享状态"
    echo "  - vLLM 集群"
    echo "  - Nginx 负载均衡"

    docker-compose --profile api up
}

# vLLM 集群模式
start_vllm() {
    echo -e "${GREEN}[启动 vLLM 集群]${NC}"
    echo "  - 需要 GPU 支持"
    echo "  - 3 个 vLLM 实例"
    echo "  - Nginx 负载均衡"

    docker-compose --profile vllm up
}

# API 服务模式
start_api() {
    echo -e "${GREEN}[启动 API 服务]${NC}"
    echo "  - 3 个 Worker"
    echo "  - Redis 状态共享"
    echo "  - Nginx 负载均衡"

    docker-compose --profile api up
}

# 完整生产环境
start_all() {
    echo -e "${GREEN}[启动完整生产环境]${NC}"
    echo "  - Redis"
    echo "  - Qdrant"
    echo "  - vLLM 集群 (3 个实例)"
    echo "  - API Workers (3 个)"
    echo "  - Nginx 负载均衡"

    docker-compose up
}

# 主入口
case "${1:-dev}" in
    dev)
        start_dev
        ;;
    prod)
        start_prod
        ;;
    vllm)
        start_vllm
        ;;
    api)
        start_api
        ;;
    all)
        start_all
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        echo -e "${RED}未知模式: $1${NC}"
        usage
        exit 1
        ;;
esac
