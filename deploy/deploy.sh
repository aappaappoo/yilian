#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Soulmeet 一键构建 + 推送脚本
#  用法: ./deploy.sh [version]
#  示例: ./deploy.sh v1.1.0（不传则默认 latest）
# ═══════════════════════════════════════════════════════════════

set -e

REGISTRY=registry.cn-hangzhou.aliyuncs.com
NAMESPACE=tb59954681
VERSION=${1:-latest}

echo "🔨 开始构建镜像 (version: ${VERSION})..."

# 1. 构建
docker compose -f docker-compose.dev.yml build

# 2. 打标签
docker tag soulmeet-backend:dev ${REGISTRY}/${NAMESPACE}/soulmeet-backend:${VERSION}
docker tag soulmeet-backend:dev ${REGISTRY}/${NAMESPACE}/soulmeet-backend:latest
docker tag soulmeet-web:dev ${REGISTRY}/${NAMESPACE}/soulmeet-web:${VERSION}
docker tag soulmeet-web:dev ${REGISTRY}/${NAMESPACE}/soulmeet-web:latest

# 3. 推送
echo "📤 推送后端镜像..."
docker push ${REGISTRY}/${NAMESPACE}/soulmeet-backend:${VERSION}
docker push ${REGISTRY}/${NAMESPACE}/soulmeet-backend:latest

echo "📤 推送前端镜像..."
docker push ${REGISTRY}/${NAMESPACE}/soulmeet-web:${VERSION}
docker push ${REGISTRY}/${NAMESPACE}/soulmeet-web:latest

echo ""
echo "✅ 推送完成！"
echo ""
echo "通知对方在服务器上执行以下命令更新："
echo "   cd /opt/soulmeet/deploy"
echo "   docker compose -f docker-compose.prod.yml pull"
echo "   docker compose -f docker-compose.prod.yml up -d"