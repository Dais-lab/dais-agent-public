#!/usr/bin/env bash
# GPU 서버에 LLM 컨테이너를 띄우는 헬퍼 스크립트.
#
# 두 가지 실행 방식을 지원한다 (.env 의 LLM_DOCKER_CONTEXT 로 선택):
#
#   (A) GPU 서버에서 직접 실행        LLM_DOCKER_CONTEXT=local
#         셋업이 필요 없고 반복 주기가 짧다. 초기 검증에 권장.
#
#   (B) 개발 서버에서 원격 실행       LLM_DOCKER_CONTEXT=<context명>  ← 팀 기본: server8
#         사전 1회 셋업:
#           ssh-copy-id -p <ssh_port> <user>@<GPU_SERVER_IP>
#           docker context create server8 \
#               --docker "host=ssh://<user>@<GPU_SERVER_IP>:<ssh_port>"
#         이 모드에서는 GPU/디스크 점검도 원격 daemon 을 통해 수행한다.
#
# 사용:
#   ./deploy.sh up          # 점검 + 빌드 + 기동
#   ./deploy.sh health      # /v1/models 확인
#   ./deploy.sh verify      # tool-call 파서 실측 검증 (가장 중요)
#   ./deploy.sh logs        # 로그 follow
#   ./deploy.sh ps          # 상태
#   ./deploy.sh gpu         # GPU 점유 확인
#   ./deploy.sh restart     # 재기동
#   ./deploy.sh recreate    # 플래그 변경 후 재생성 (restart 로는 안 바뀜)
#   ./deploy.sh down        # 종료 + 컨테이너 제거
#   ./deploy.sh shell       # 컨테이너 셸 진입
#   ./deploy.sh debug       # 크래시 루프 시 root cause 추출

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"

# 설정의 단일 출처는 저장소 루트의 .env 다 (LLM_* 섹션).
# 단, GPU 서버에 이 폴더만 복사해 local 모드로 돌리는 경우를 위해
# 폴더 안에 .env 가 있으면 그쪽을 우선한다 — 루트 .env 에는 DB/MinIO/Airflow
# 비밀값이 함께 들어 있어 다른 서버로 통째로 옮기면 안 되기 때문이다.
if [ -f "$HERE/.env" ]; then
    ENV_FILE="$HERE/.env"
elif [ -f "$REPO_ROOT/.env" ]; then
    ENV_FILE="$REPO_ROOT/.env"
else
    echo "❌ .env 없음 → 저장소 루트에서 'make init' 후 LLM_* 값을 채우세요." >&2
    echo "   (GPU 서버에서 단독 실행하려면 이 폴더에 LLM_* 만 담은 .env 를 두세요)" >&2
    exit 1
fi
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a

# 기본값은 원격(server8) — 개발 서버에서 무심코 실행했을 때 그 서버의 daemon 에
# 조용히 띄우는 사고를 막는다. GPU 서버에서 직접 돌릴 때만 .env 에서 local 로 바꾼다.
CONTEXT="${LLM_DOCKER_CONTEXT:-server8}"
HOST_IP="${LLM_HOST_IP:-127.0.0.1}"
HOST_PORT="${LLM_HOST_PORT:-8000}"
IMAGE_REF="${VLLM_IMAGE:-vllm/vllm-openai:v0.26.0}"
CONTAINER=dais-llm

# 필요한 여유 VRAM (MiB). GPU 총량 × LLM_GPU_MEM_UTIL 보다 커야 한다.
# 기본값은 util=0.45 (97,887 MiB GPU 기준 ≈ 44,000 + 여유) 에 맞춰져 있다.
# ⚠️ .env 에서 LLM_GPU_MEM_UTIL 을 바꾸면 LLM_REQUIRED_FREE_MIB 도 같이 바꾼다.
REQUIRED_FREE_MIB="${LLM_REQUIRED_FREE_MIB:-47000}"

# ──────────────────────────────────────────────────────────────────────
# Helpers
#   원격 context 에서도 올바른 대상을 보도록 모든 docker 호출은 dkr() 를 거친다.
#   (직접 'docker ...' 를 부르면 개발 서버의 daemon 을 보게 되어 잘못된 판정을 한다)
# ──────────────────────────────────────────────────────────────────────
dkr() {
    if [ "$CONTEXT" = "local" ]; then
        docker "$@"
    else
        docker --context "$CONTEXT" "$@"
    fi
}

COMPOSE=(compose -f "$HERE/docker-compose.yml" --env-file "$ENV_FILE")

# endpoint 대상 호스트 — 원격 실행 시 127.0.0.1 은 개발 서버 자신을 가리키므로 쓰면 안 된다.
if [ "$CONTEXT" = "local" ]; then
    TARGET_HOST=127.0.0.1
else
    TARGET_HOST="$HOST_IP"
    if [ "$TARGET_HOST" = "127.0.0.1" ]; then
        echo "⚠️  LLM_DOCKER_CONTEXT=$CONTEXT 인데 LLM_HOST_IP 가 설정되지 않았습니다." >&2
        echo "    health/verify 가 잘못된 호스트를 검사합니다 — .env 에 LLM_HOST_IP 를 채우세요." >&2
    fi
fi

require_context() {
    if [ "$CONTEXT" = "local" ]; then
        command -v docker >/dev/null || {
            echo "❌ docker 를 찾을 수 없습니다. GPU 서버 호스트에서 실행하세요." >&2
            exit 1
        }
        return
    fi
    if ! docker context inspect "$CONTEXT" >/dev/null 2>&1; then
        cat <<EOF >&2
❌ docker context '$CONTEXT' 가 없습니다. 한 번만 등록하세요:

    docker context create $CONTEXT \\
        --docker "host=ssh://<user>@${LLM_HOST_IP:-<GPU_SERVER_IP>}:<ssh_port>"

또는 GPU 서버에서 직접 실행: .env 에 LLM_DOCKER_CONTEXT=local
EOF
        exit 1
    fi
    docker --context "$CONTEXT" ps >/dev/null 2>&1 || {
        echo "❌ context '$CONTEXT' 의 SSH 연결 실패. 'ssh <user>@${LLM_HOST_IP} echo OK' 부터 검증하세요." >&2
        exit 1
    }
}

# GPU 여유 조회 — local 이면 호스트 nvidia-smi, 원격이면 대상 daemon 을 거친다.
# 원격에서는 두 경로를 순서대로 시도한다:
#   ① 실행 중인 컨테이너에 exec  — nvidia-smi 는 NVIDIA 런타임이 주입해주므로 항상 있다.
#   ② 베이스 이미지로 일회용 run — 컨테이너가 내려간 상태(up 직전 check_vram)에서 필요.
# ①을 먼저 두는 이유: compose 가 빌드한 이미지는 dais-llm-llm 이고 베이스 이미지는
# BuildKit 빌드 시 image store 에 남지 않을 수 있어 ②가 조용히 실패한다(실측).
gpu_query() {   # $1: --query-gpu 값
    if [ "$CONTEXT" = "local" ] && command -v nvidia-smi >/dev/null 2>&1; then
        nvidia-smi --query-gpu="$1" --format=csv,noheader,nounits 2>/dev/null || true
    elif dkr ps --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTAINER"; then
        dkr exec "$CONTAINER" nvidia-smi \
            --query-gpu="$1" --format=csv,noheader,nounits 2>/dev/null || true
    elif dkr image inspect "$IMAGE_REF" >/dev/null 2>&1; then
        dkr run --rm --gpus all --entrypoint nvidia-smi "$IMAGE_REF" \
            --query-gpu="$1" --format=csv,noheader,nounits 2>/dev/null || true
    fi
}

check_vram() {
    local free
    free="$(gpu_query memory.free | head -1 | tr -dc '0-9')"
    if [ -z "$free" ]; then
        echo "⚠️  GPU 여유를 확인하지 못했습니다 — 점검을 건너뜁니다."
        echo "   컨테이너가 내려간 상태라면 베이스 이미지가 대상 daemon 에 있어야 합니다:"
        echo "     docker --context ${CONTEXT} pull ${IMAGE_REF}"
        return 0
    fi
    echo "▶ GPU 여유: ${free} MiB (필요 ≈ ${REQUIRED_FREE_MIB} MiB)"
    if [ "$free" -lt "$REQUIRED_FREE_MIB" ]; then
        echo "❌ VRAM 부족 — 다른 작업이 GPU 를 점유 중입니다." >&2
        if [ "$CONTEXT" = "local" ] && command -v nvidia-smi >/dev/null 2>&1; then
            nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv >&2
        fi
        echo "   → 해당 작업 종료를 기다리거나 .env 의 LLM_GPU_MEM_UTIL 을 낮추세요." >&2
        exit 1
    fi
}

check_port() {
    if dkr ps --format '{{.Names}} {{.Ports}}' 2>/dev/null \
        | grep -v "^${CONTAINER} " | grep -q ":${HOST_PORT}->"; then
        echo "❌ 포트 ${HOST_PORT} 를 다른 컨테이너가 점유 중입니다:" >&2
        dkr ps --format '   {{.Names}}  {{.Ports}}' | grep ":${HOST_PORT}->" >&2
        echo "   → 해당 컨테이너를 내리거나 .env 의 LLM_HOST_PORT 를 바꾸세요." >&2
        exit 1
    fi
}

check_disk() {
    local cache="${HF_CACHE_DIR:-}"
    [ -n "$cache" ] || { echo "⚠️  HF_CACHE_DIR 미설정 — .env 확인"; return 0; }
    if [ "$CONTEXT" = "local" ]; then
        [ -d "$cache" ] || { echo "⚠️  캐시 경로 없음: $cache"; return 0; }
        local avail
        avail=$(df -BG --output=avail "$cache" 2>/dev/null | tail -1 | tr -dc '0-9')
        [ -n "$avail" ] && echo "▶ 캐시 디스크 여유: ${avail}GB (모델 약 7GB 필요)"
        [ -n "$avail" ] && [ "$avail" -lt 20 ] && echo "   ⚠️ 여유가 빠듯합니다."
    else
        echo "▶ 디스크 점검은 원격 모드에서 생략합니다 (GPU 서버에서 df -h 로 확인하세요)."
    fi
    return 0
}

# ──────────────────────────────────────────────────────────────────────
# Subcommands
# ──────────────────────────────────────────────────────────────────────
case "${1:-up}" in
    build)
        require_context
        dkr "${COMPOSE[@]}" build
        ;;
    up)
        require_context
        check_port
        echo "▶ 설정: ${ENV_FILE}  (context=${CONTEXT}, util=${LLM_GPU_MEM_UTIL:-?})"
        echo "▶ 빌드 (첫 회는 vLLM 이미지 pull 로 시간이 걸립니다)"
        dkr "${COMPOSE[@]}" build
        check_vram          # 이미지가 준비된 뒤에 조회해야 원격 모드에서도 동작한다
        check_disk
        echo "▶ 기동"
        dkr "${COMPOSE[@]}" up -d
        cat <<EOF

✅ 컨테이너 기동됨.
   주소:   http://${TARGET_HOST}:${HOST_PORT}/v1/models
   진행:   $0 logs
   준비:   $0 health
   검증:   $0 verify     ← tool-call 파서 확인, 반드시 실행

⚠️  첫 기동은 모델 다운로드(약 7GB) + 로드로 시간이 걸립니다.
    'Application startup complete' 전에는 포트가 열리지 않습니다.
EOF
        ;;
    health)
        if curl -sf "http://${TARGET_HOST}:${HOST_PORT}/v1/models" | head -c 2000; then
            echo; echo "✅ 응답 정상 (dais-llm alias 확인)"
        else
            echo "❌ 응답 없음 — 로딩 중이거나 크래시. '$0 logs' 확인"; exit 1
        fi
        ;;
    verify)
        script="$HERE/verify_toolcall.py"
        [ -f "$script" ] || { echo "❌ verify_toolcall.py 없음: $script" >&2; exit 1; }
        LLM_URL="http://${TARGET_HOST}:${HOST_PORT}" \
        LLM_MODEL="${LLM_MODEL:-dais-llm}" \
        LLM_API_KEY="${LLM_API_KEY:-local}" \
            python3 "$script"
        ;;
    logs)     require_context; dkr "${COMPOSE[@]}" logs -f ;;
    ps)       require_context; dkr "${COMPOSE[@]}" ps ;;
    restart)  require_context; dkr "${COMPOSE[@]}" restart ;;
    recreate)
        require_context; check_port; check_vram
        dkr "${COMPOSE[@]}" up -d --force-recreate
        echo "▶ 재생성 완료. '$0 logs' 로 진행 확인."
        ;;
    down)     require_context; dkr "${COMPOSE[@]}" down ;;
    shell)    require_context; dkr "${COMPOSE[@]}" exec llm bash ;;
    gpu)
        require_context
        echo "── memory.used / memory.free / utilization ──"
        gpu_out="$(gpu_query memory.used,memory.free,utilization.gpu)"
        if [ -n "$gpu_out" ]; then
            echo "$gpu_out"
        else
            # 침묵하지 않는다 — 예전에는 빈 출력이라 조회 실패를 알아채기 어려웠다.
            echo "⚠️  조회 실패 — 컨테이너가 내려가 있고 베이스 이미지도 대상 daemon 에 없습니다."
            echo "   → docker --context ${CONTEXT} pull ${IMAGE_REF}"
        fi
        if [ "$CONTEXT" = "local" ] && command -v nvidia-smi >/dev/null 2>&1; then
            echo "── 점유 프로세스 ──"
            nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
        fi
        ;;
    debug)
        require_context
        dkr logs "$CONTAINER" 2>&1 \
          | grep -niE "error|cuda|out of memory|oom|nccl|traceback|killed|driver|root cause|mamba|cache" \
          | tail -40
        ;;
    *)
        echo "사용: $0 {build|up|health|verify|logs|ps|gpu|restart|recreate|down|shell|debug}" >&2
        exit 1
        ;;
esac
