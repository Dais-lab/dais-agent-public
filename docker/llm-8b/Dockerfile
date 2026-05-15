# vLLM (OpenAI 호환 endpoint) 베이스 이미지.
# 별도 GPU 서버에서 google/gemma-4-E4B-it 모델 서빙용 (소형 8B 변형).
#
# 모델 가중치는 HuggingFace Hub 에서 컨테이너 첫 기동 시 다운로드되어
# /root/.cache/huggingface (named volume) 에 캐시된다.
# Gemma 는 HF gated repo 라 HUGGING_FACE_HUB_TOKEN 이 필요할 수 있음.

FROM vllm/vllm-openai:latest

# 컨테이너 entrypoint 가 vllm server 이므로 별도 설정 불필요.
# 실제 모델/포트/메모리 옵션은 docker-compose.yml 의 command 에서 지정.
