#!/usr/bin/env bash
# 개발 서버에서 실행 → 별도 GPU 서버 의 docker daemon 에
# google/gemma-4-26B-A4B-it LLM 컨테이너를 띄우는 헬퍼 스크립트.
#
# 전제 (사전 1회 셋업):
#   1) LLM_HOST_IP 환경변수에 GPU 서버 IP 설정 (또는 본 스크립트의 HOST_IP 기본값 수정)
#   2) ~/.ssh/config 에 적절한 SSH 키 + 별칭 등록
#   3) docker context 등록:
#        docker context create $CONTEXT \
#            --docker "host=ssh://<user>@${LLM_HOST_IP}:<ssh_port>"
#
# 사용:
#   ./deploy.sh build       # GPU 서버에 이미지 빌드
#   ./deploy.sh up          # 빌드 + 기동 (백그라운드)
#   ./deploy.sh logs        # 로그 follow
#   ./deploy.sh ps          # 상태 확인
#   ./deploy.sh restart     # 재기동
#   ./deploy.sh down        # 종료 + 컨테이너 제거
#   ./deploy.sh shell       # 컨테이너 셸 진입
#   ./deploy.sh clean       # 컨테이너 + 볼륨 모두 삭제 (모델 캐시도 사라짐, 주의)

set -euo pipefail

CONTEXT="${LLM_DOCKER_CONTEXT:-llm-host}"
HOST_IP="${LLM_HOST_IP:-<GPU_SERVER_IP>}"
HOST_PORT="${LLM_HOST_PORT:-8005}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE=(docker --context "$CONTEXT" compose -f "$HERE/docker-compose.yml")

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
require_context() {
    if ! docker context inspect "$CONTEXT" >/dev/null 2>&1; then
        cat <<EOF >&2
❌ docker context '$CONTEXT' 가 없음.
다음 명령으로 한 번만 등록하세요:

    docker context create $CONTEXT \\
        --docker "host=ssh://<user>@$HOST_IP:<ssh_port>"

(SSH 키 인증 셋업도 미리 — 'ssh-copy-id -p <ssh_port> <user>@$HOST_IP')
EOF
        exit 1
    fi
    if ! docker --context "$CONTEXT" ps >/dev/null 2>&1; then
        echo "❌ context '$CONTEXT' 의 SSH 연결 실패. 'ssh server8 echo OK' 부터 검증하세요." >&2
        exit 1
    fi
}

# ──────────────────────────────────────────────────────────────────────
# Subcommands
# ──────────────────────────────────────────────────────────────────────
cmd="${1:-up}"
case "$cmd" in
    build)
        require_context
        "${COMPOSE[@]}" build
        ;;
    up)
        require_context
        echo "▶ 빌드 (8번 서버에서 이미지 생성 — 첫 회 5~10분)"
        "${COMPOSE[@]}" build
        echo "▶ 기동"
        "${COMPOSE[@]}" up -d
        echo
        echo "✅ 기동 완료."
        echo "   주소:   http://$HOST_IP:$HOST_PORT/v1/models"
        echo "   로그:   $0 logs"
        echo "   상태:   $0 ps"
        echo
        echo "⚠️  첫 기동 시 모델(gemma-4-26B) 다운로드에 시간 걸림."
        echo "   $0 logs 로 'Application startup complete' 메시지 확인 후 사용 권장."
        ;;
    logs)
        require_context
        "${COMPOSE[@]}" logs -f
        ;;
    ps)
        require_context
        "${COMPOSE[@]}" ps
        ;;
    restart)
        require_context
        "${COMPOSE[@]}" restart
        ;;
    down)
        require_context
        "${COMPOSE[@]}" down
        ;;
    shell)
        require_context
        "${COMPOSE[@]}" exec llm bash
        ;;
    clean)
        require_context
        echo "⚠️  컨테이너 + 볼륨(모델 캐시 dais_llm_hf_cache) 모두 삭제합니다."
        read -r -p "계속하려면 'yes' 입력: " confirm
        [ "$confirm" = "yes" ] || { echo "취소"; exit 0; }
        "${COMPOSE[@]}" down -v
        ;;
    *)
        echo "사용: $0 {build|up|logs|ps|restart|down|shell|clean}" >&2
        exit 1
        ;;
esac
