#!/bin/sh
set -e

CERT_DIR="/etc/nginx/ssl"
CERT_FILE="$CERT_DIR/fullchain.pem"
KEY_FILE="$CERT_DIR/privkey.pem"

# ── 检查 SSL 证书，不存在则自动生成自签名证书 ──
if [ ! -s "$CERT_FILE" ] || [ ! -s "$KEY_FILE" ]; then
  echo "=============================================="
  echo "⚠️  未检测到 SSL 证书，正在自动生成自签名证书..."
  echo "=============================================="
  mkdir -p "$CERT_DIR"
  SSL_DOMAIN="${SSL_DOMAIN:-soulmeet}"

  # 判断 SSL_DOMAIN 是 IP 地址还是域名，生成对应的 SAN
  # 现代浏览器（Chrome 58+）要求 SAN 匹配，仅 CN 会被忽略
  if echo "$SSL_DOMAIN" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
    SAN="IP:${SSL_DOMAIN}"
  else
    SAN="DNS:${SSL_DOMAIN}"
  fi

  openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE" \
    -subj "/CN=${SSL_DOMAIN}/O=Soulmeet/C=CN" \
    -addext "subjectAltName=${SAN}"
  echo "✅ 自签名证书已生成（CN=${SSL_DOMAIN}, SAN=${SAN}，有效期 365 天）。"
  echo ""
  echo "📌 首次访问时浏览器会提示"不安全"，请点击「高级 → 继续访问」。"
  echo "📌 可通过环境变量 SSL_DOMAIN 设置你的 IP 或域名，例如："
  echo "   SSL_DOMAIN=203.0.113.10  （IP 地址）"
  echo "   SSL_DOMAIN=example.com   （域名）"
  echo "📌 生产环境建议挂载正式证书到 ./certs/ 目录："
  echo "   - certs/fullchain.pem  （证书链）"
  echo "   - certs/privkey.pem    （私钥）"
  echo "=============================================="
fi

exec nginx -g "daemon off;"
