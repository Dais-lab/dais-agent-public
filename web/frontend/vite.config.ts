import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// 백엔드 URL 은 VITE_API_TARGET 환경변수로 override 가능.
// 기본은 호스트의 8005. 백엔드가 dev 컨테이너 내부에서 다른 포트(예: Claude Code IDE forwarding)로 노출돼 있다면
//   VITE_API_TARGET=http://localhost:58195 npm run dev
// 식으로 실행.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.VITE_API_TARGET ?? "http://localhost:8005";
  return {
    plugins: [react()],
    server: {
      host: "0.0.0.0",
      port: 5173,
      proxy: {
        "/api": { target, changeOrigin: true },
      },
    },
  };
});
