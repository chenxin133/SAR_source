import { defineConfig, loadEnv } from 'vite';
import vue from '@vitejs/plugin-vue';
export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, '.', '');
    const proxyTarget = env.VITE_PROXY_TARGET;
    return {
        plugins: [vue()],
        server: {
            host: true,
            port: 5173,
            strictPort: false,
            proxy: proxyTarget
                ? {
                    '/api': {
                        target: proxyTarget,
                        changeOrigin: true
                    }
                }
                : undefined
        },
        test: {
            environment: 'happy-dom',
            setupFiles: ['src/test/setup.ts'],
            coverage: {
                provider: 'v8'
            }
        }
    };
});
