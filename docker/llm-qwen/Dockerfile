# vLLM (OpenAI 호환 endpoint) 베이스 이미지.
# 별도 GPU 서버에서 Qwen/Qwen3.6-35B-A3B-FP8 모델 서빙용.
#
# 모델 가중치(37.5GB)는 HuggingFace Hub 에서 컨테이너 첫 기동 시 다운로드되어
# HF_CACHE_DIR (호스트 bind mount) 에 캐시된다.
# Apache 2.0 · 비게이트 모델이라 HUGGING_FACE_HUB_TOKEN 은 불필요.

# 이미지 태그는 고정한다 — tool-call parser 의 동작이 vLLM 버전에 따라 달라지므로
# :latest 로 두면 이미지가 갱신될 때 에이전트가 예고 없이 깨질 수 있다.
# Qwen3.6 은 vllm>=0.19.0 필요.
ARG VLLM_IMAGE=vllm/vllm-openai:v0.26.0
FROM ${VLLM_IMAGE}

# 컨테이너 entrypoint 가 vllm server 이므로 별도 설정 불필요.
# 실제 모델/포트/메모리 옵션은 docker-compose.yml 의 command 에서 지정.
